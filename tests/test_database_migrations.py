"""Regression tests for the legacy users-role schema migration."""

import sqlite3
import unittest

from app import migrate_user_roles


class UserRoleMigrationTests(unittest.TestCase):
    def make_legacy_database(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        con.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('client', 'photographer')),
                created_at TEXT NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE,
                display_name TEXT NOT NULL,
                FOREIGN KEY(user_id) REFERENCES users(id)
            )
        """)
        con.execute("""
            INSERT INTO users (name, email, password_hash, role, created_at)
            VALUES ('Existing User', 'existing@example.test', 'hash', 'photographer', '2025-01-01')
        """)
        user_id = con.execute(
            "SELECT id FROM users WHERE email = 'existing@example.test'"
        ).fetchone()["id"]
        con.execute(
            "INSERT INTO providers (user_id, display_name) VALUES (?, ?)",
            (user_id, "Existing Creative"),
        )
        con.commit()
        return con, user_id

    def test_migration_preserves_users_and_dependent_foreign_keys(self):
        con, user_id = self.make_legacy_database()
        try:
            migrate_user_roles(con)

            user = con.execute(
                "SELECT id, name, email, role FROM users WHERE id = ?",
                (user_id,),
            ).fetchone()
            provider = con.execute(
                "SELECT user_id, display_name FROM providers WHERE user_id = ?",
                (user_id,),
            ).fetchone()

            self.assertEqual(user["email"], "existing@example.test")
            self.assertEqual(user["role"], "photographer")
            self.assertEqual(provider["user_id"], user_id)
            self.assertEqual(provider["display_name"], "Existing Creative")
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual(
                con.execute("PRAGMA foreign_keys").fetchone()[0], 1
            )
        finally:
            con.close()

    def test_migration_is_safe_to_run_again(self):
        con, user_id = self.make_legacy_database()
        try:
            migrate_user_roles(con)
            migrate_user_roles(con)

            self.assertEqual(
                con.execute(
                    "SELECT COUNT(*) FROM users WHERE id = ?", (user_id,)
                ).fetchone()[0],
                1,
            )
            self.assertEqual(con.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            con.close()


if __name__ == "__main__":
    unittest.main()
