# tests/test_wardrobe_service.py
import unittest
import uuid
from fastapi import HTTPException

print("DEBUG: Attempting to import test_wardrobe_service.py and its dependencies.")

from outfitai_project.services import wardrobe_service, user_service 
from outfitai_project.models.user_models import UserCreate
from outfitai_project.models.outfit_models import WardrobeItemCreate, WardrobeItemUpdate, ItemCategory, WardrobeItem

print("DEBUG: Successfully imported dependencies for test_wardrobe_service.py.")


class TestWardrobeService(unittest.TestCase):

    def setUp(self):
        user_service.db_users.clear()
        wardrobe_service.db_wardrobe_items.clear()
        # print(f"\n--- Running test: {self.id()} ---")
        # print("setUp: db_users and db_wardrobe_items cleared.")
        
        self.test_user_data = UserCreate(email="wardrobe_owner@example.com", password="password")
        self.test_user = user_service.create_user_in_db(self.test_user_data)
        # print(f"setUp: Created test user {self.test_user.id}")

    def tearDown(self):
        # print("tearDown: Test finished for {self.id()}.")
        pass

    def test_add_wardrobe_item_success(self):
        # print("test_add_wardrobe_item_success: Starting.")
        item_data = WardrobeItemCreate(
            name="Test Jacket",
            category=ItemCategory.OUTERWEAR,
            color="Black"
        )
        created_item = wardrobe_service.add_wardrobe_item_for_user(self.test_user.id, item_data)
        
        self.assertIsInstance(created_item, WardrobeItem)
        self.assertEqual(created_item.name, item_data.name)
        self.assertEqual(created_item.user_id, self.test_user.id)
        self.assertIn(created_item.id, wardrobe_service.db_wardrobe_items)
        # print(f"test_add_wardrobe_item_success: Item {created_item.id} added.")

    def test_add_wardrobe_item_user_not_found(self):
        # print("test_add_wardrobe_item_user_not_found: Starting.")
        non_existent_user_id = uuid.uuid4()
        item_data = WardrobeItemCreate(name="Test Item", category=ItemCategory.TOP)
        
        with self.assertRaises(HTTPException) as cm:
            wardrobe_service.add_wardrobe_item_for_user(non_existent_user_id, item_data)
        
        self.assertEqual(cm.exception.status_code, 404)
        self.assertIn("User with id", cm.exception.detail)
        # print("test_add_wardrobe_item_user_not_found: Correctly raised 404 for non-existent user.")

    def test_get_wardrobe_items_for_user(self):
        # print("test_get_wardrobe_items_for_user: Starting.")
        item_data1 = WardrobeItemCreate(name="Shirt", category=ItemCategory.TOP)
        item_data2 = WardrobeItemCreate(name="Pants", category=ItemCategory.BOTTOM)
        wardrobe_service.add_wardrobe_item_for_user(self.test_user.id, item_data1)
        wardrobe_service.add_wardrobe_item_for_user(self.test_user.id, item_data2)

        other_user = user_service.create_user_in_db(UserCreate(email="other@example.com", password="password123")) # Fixed
        wardrobe_service.add_wardrobe_item_for_user(other_user.id, WardrobeItemCreate(name="OtherUserItem", category=ItemCategory.ACCESSORY))

        user_items = wardrobe_service.get_wardrobe_items_for_user(self.test_user.id)
        self.assertEqual(len(user_items), 2)
        item_names = {item.name for item in user_items}
        self.assertIn("Shirt", item_names)
        self.assertIn("Pants", item_names)
        # print("test_get_wardrobe_items_for_user: Retrieved correct items for user.")

    def test_get_wardrobe_item_by_id_found_and_owned(self):
        # print("test_get_wardrobe_item_by_id_found_and_owned: Starting.")
        item_data = WardrobeItemCreate(name="My Special Item", category=ItemCategory.DRESS)
        created_item = wardrobe_service.add_wardrobe_item_for_user(self.test_user.id, item_data)

        retrieved_item = wardrobe_service.get_wardrobe_item_by_id(created_item.id, user_id=self.test_user.id)
        self.assertIsNotNone(retrieved_item)
        self.assertEqual(retrieved_item.id, created_item.id)

        retrieved_item_no_owner_check = wardrobe_service.get_wardrobe_item_by_id(created_item.id)
        self.assertIsNotNone(retrieved_item_no_owner_check)
        self.assertEqual(retrieved_item_no_owner_check.id, created_item.id)
        # print("test_get_wardrobe_item_by_id_found_and_owned: Item retrieved.")


    def test_get_wardrobe_item_by_id_forbidden(self):
        # print("test_get_wardrobe_item_by_id_forbidden: Starting.")
        other_user = user_service.create_user_in_db(UserCreate(email="other_owner@example.com", password="password123")) # Fixed
        item_data_other = WardrobeItemCreate(name="Other User's Item", category=ItemCategory.SHOES)
        other_item = wardrobe_service.add_wardrobe_item_for_user(other_user.id, item_data_other)

        with self.assertRaises(HTTPException) as cm:
            wardrobe_service.get_wardrobe_item_by_id(other_item.id, user_id=self.test_user.id)
        self.assertEqual(cm.exception.status_code, 403)
        # print("test_get_wardrobe_item_by_id_forbidden: Correctly raised 403.")


    def test_update_wardrobe_item_success(self):
        # print("test_update_wardrobe_item_success: Starting.")
        item_data = WardrobeItemCreate(name="Old Name", category=ItemCategory.ACCESSORY)
        created_item = wardrobe_service.add_wardrobe_item_for_user(self.test_user.id, item_data)
        
        update_payload = WardrobeItemUpdate(name="New Name", color="Gold")
        updated_item = wardrobe_service.update_wardrobe_item_for_user(created_item.id, self.test_user.id, update_payload)
        
        self.assertIsNotNone(updated_item)
        self.assertEqual(updated_item.name, "New Name")
        self.assertEqual(updated_item.color, "Gold")
        # print("test_update_wardrobe_item_success: Item updated.")

    def test_update_wardrobe_item_not_owned(self):
        # print("test_update_wardrobe_item_not_owned: Starting.")
        other_user = user_service.create_user_in_db(UserCreate(email="another@example.com", password="password123")) # Fixed
        item_belonging_to_other = wardrobe_service.add_wardrobe_item_for_user(other_user.id, WardrobeItemCreate(name="Other's Hat", category=ItemCategory.ACCESSORY))
        
        update_payload = WardrobeItemUpdate(name="Attempted Update")
        with self.assertRaises(HTTPException) as cm:
            wardrobe_service.update_wardrobe_item_for_user(item_belonging_to_other.id, self.test_user.id, update_payload)
        self.assertEqual(cm.exception.status_code, 403)
        # print("test_update_wardrobe_item_not_owned: Correctly raised 403.")

    def test_delete_wardrobe_item_success(self):
        # print("test_delete_wardrobe_item_success: Starting.")
        item_data = WardrobeItemCreate(name="To Be Deleted", category=ItemCategory.OTHER)
        created_item = wardrobe_service.add_wardrobe_item_for_user(self.test_user.id, item_data)
        
        self.assertIn(created_item.id, wardrobe_service.db_wardrobe_items)
        deleted = wardrobe_service.delete_wardrobe_item_for_user(created_item.id, self.test_user.id)
        self.assertTrue(deleted)
        self.assertNotIn(created_item.id, wardrobe_service.db_wardrobe_items)
        # print("test_delete_wardrobe_item_success: Item deleted.")

    def test_delete_wardrobe_item_not_owned(self):
        # print("test_delete_wardrobe_item_not_owned: Starting.")
        other_user = user_service.create_user_in_db(UserCreate(email="yet_another@example.com", password="password123")) # Fixed
        item_belonging_to_other = wardrobe_service.add_wardrobe_item_for_user(other_user.id, WardrobeItemCreate(name="Untouchable", category=ItemCategory.OTHER))

        with self.assertRaises(HTTPException) as cm:
            wardrobe_service.delete_wardrobe_item_for_user(item_belonging_to_other.id, self.test_user.id)
        self.assertEqual(cm.exception.status_code, 403)
        self.assertIn(item_belonging_to_other.id, wardrobe_service.db_wardrobe_items)
        # print("test_delete_wardrobe_item_not_owned: Correctly raised 403.")


if __name__ == '__main__':
    print("DEBUG: test_wardrobe_service.py is being run directly as __main__.")
    unittest.main()