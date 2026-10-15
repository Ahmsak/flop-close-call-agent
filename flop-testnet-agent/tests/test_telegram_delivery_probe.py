import unittest
from telegram_bridge import check_owner


class OwnerBindingTests(unittest.TestCase):
    def test_private_id_allowlist_and_username_all_required(self):
        chat={'id':123,'type':'private','username':'owner'}
        self.assertEqual(check_owner('123','123',chat,'owner')['status'],'VERIFIED')
        for changed in ({**chat,'username':'different'},{**chat,'username':None},
                        {**chat,'id':456},{**chat,'type':'group'}):
            self.assertEqual(check_owner('123','123',changed,'owner')['status'],'NOT_SENT')
        self.assertEqual(check_owner('123','456',chat,'owner')['status'],'NOT_SENT')
        self.assertEqual(check_owner('-123','-123',chat,'owner')['status'],'NOT_SENT')

    def test_display_name_does_not_authorize(self):
        chat={'id':123,'type':'private','username':'different','name':'owner'}
        self.assertEqual(check_owner('123','123',chat,'owner')['requests'],0)
        self.assertEqual(check_owner('123','123',chat,'owner')['status'],'NOT_SENT')
