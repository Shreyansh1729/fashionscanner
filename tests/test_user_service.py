# tests/test_user_service.py
import unittest
import uuid
from fastapi import HTTPException

print("DEBUG: Attempting to import test_user_service.py and its dependencies.")

# Adjust the import path based on how you run tests.
# If running `python -m unittest discover` from project root, this should work:
from outfitai_project.services import user_service
from outfitai_project.models.user_models import UserCreate, UserUpdate, User, BodyType, SkinTone

print("DEBUG: Successfully imported dependencies for test_user_service.py.")


class TestUserService(unittest.TestCase):

    def setUp(self):
        """This method is called before each test."""
        # Reset the in-memory database for each test to ensure isolation
        user_service.db_users.clear()
        # print(f"\n--- Running test: {self.id()} ---") # Can be verbose
        # print("setUp: db_users cleared.")

    def tearDown(self):
        """This method is called after each test."""
        # print("tearDown: Test finished for {self.id()}.")
        pass # No specific cleanup needed for in-memory if setUp clears it.

    def test_create_user_success(self):
        # print("test_create_user_success: Starting.")
        user_data = UserCreate(
            email="test@example.com",
            password="password123",
            username="testuser",
            gender="Male",
            age_range="25-30",
            body_type=BodyType.MESOMORPH,
            skin_tone=SkinTone.NEUTRAL,
            height_cm=180,
            weight_kg=75.0
        )
        created_user = user_service.create_user_in_db(user_data)
        self.assertIsInstance(created_user, User)
        self.assertEqual(created_user.email, user_data.email)
        self.assertEqual(created_user.username, user_data.username)
        self.assertTrue(created_user.is_active)
        self.assertIn(created_user.id, user_service.db_users) # Check if stored
        # print(f"test_create_user_success: User {created_user.id} created.")

    def test_create_user_duplicate_email(self):
        # print("test_create_user_duplicate_email: Starting.")
        user_data1 = UserCreate(email="duplicate@example.com", password="password1")
        user_service.create_user_in_db(user_data1) 

        user_data2 = UserCreate(email="duplicate@example.com", password="password2")
        with self.assertRaises(HTTPException) as cm:
            user_service.create_user_in_db(user_data2)
        
        self.assertEqual(cm.exception.status_code, 400)
        self.assertEqual(cm.exception.detail, "Email already registered.")
        # print("test_create_user_duplicate_email: Correctly raised HTTPException for duplicate email.")

    def test_get_user_by_id_found(self):
        # print("test_get_user_by_id_found: Starting.")
        user_data = UserCreate(email="get_id@example.com", password="password")
        created_user = user_service.create_user_in_db(user_data)
        
        retrieved_user = user_service.get_user_by_id(created_user.id)
        self.assertIsNotNone(retrieved_user)
        self.assertEqual(retrieved_user.id, created_user.id)
        # print(f"test_get_user_by_id_found: User {created_user.id} retrieved successfully.")

    def test_get_user_by_id_not_found(self):
        # print("test_get_user_by_id_not_found: Starting.")
        non_existent_id = uuid.uuid4()
        retrieved_user = user_service.get_user_by_id(non_existent_id)
        self.assertIsNone(retrieved_user)
        # print("test_get_user_by_id_not_found: Correctly returned None for non-existent ID.")

    def test_get_user_by_email_found(self):
        # print("test_get_user_by_email_found: Starting.")
        user_data = UserCreate(email="get_email@example.com", password="password")
        user_service.create_user_in_db(user_data)

        retrieved_user = user_service.get_user_by_email("get_email@example.com")
        self.assertIsNotNone(retrieved_user)
        self.assertEqual(retrieved_user.email, "get_email@example.com")
        # print("test_get_user_by_email_found: User retrieved successfully by email.")

    def test_get_user_by_email_not_found(self):
        # print("test_get_user_by_email_not_found: Starting.")
        retrieved_user = user_service.get_user_by_email("non_existent@example.com")
        self.assertIsNone(retrieved_user)
        # print("test_get_user_by_email_not_found: Correctly returned None for non-existent email.")

    def test_update_user_success(self):
        # print("test_update_user_success: Starting.")
        user_data = UserCreate(email="update_me@example.com", password="password", username="initial_username")
        created_user = user_service.create_user_in_db(user_data)

        update_payload = UserUpdate(username="updated_username", height_cm=175)
        updated_user = user_service.update_user_in_db(created_user.id, update_payload)

        self.assertIsNotNone(updated_user)
        self.assertEqual(updated_user.username, "updated_username")
        self.assertEqual(updated_user.height_cm, 175)
        self.assertEqual(updated_user.email, "update_me@example.com") 
        # print("test_update_user_success: User updated successfully.")

    def test_update_user_not_found(self):
        # print("test_update_user_not_found: Starting.")
        non_existent_id = uuid.uuid4()
        update_payload = UserUpdate(username="should_not_matter")
        updated_user = user_service.update_user_in_db(non_existent_id, update_payload)
        self.assertIsNone(updated_user)
        # print("test_update_user_not_found: Correctly returned None for non-existent user update.")

    def test_get_all_users(self):
        # print("test_get_all_users: Starting.")
        user_data1 = UserCreate(email="user1@example.com", password="password123") # Fixed
        user_data2 = UserCreate(email="user2@example.com", password="password456") # Fixed
        user_service.create_user_in_db(user_data1)
        user_service.create_user_in_db(user_data2)

        all_users = user_service.get_all_users_in_db()
        self.assertEqual(len(all_users), 2)
        emails = {user.email for user in all_users}
        self.assertIn("user1@example.com", emails)
        self.assertIn("user2@example.com", emails)
        # print("test_get_all_users: Retrieved all users correctly.")



if __name__ == '__main__':
    print("DEBUG: test_user_service.py is being run directly as __main__.")
    unittest.main()