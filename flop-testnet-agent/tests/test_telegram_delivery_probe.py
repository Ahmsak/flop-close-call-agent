import unittest
from telegram_bridge import check_owner, delivery_result, response_excerpt


class OwnerBindingTests(unittest.TestCase):
    def test_safe_response_and_optional_fields(self):
        body={'ok':True,'result':{'message_id':42,'date':1700000000,
            'from':{'id':99,'username':'fixture_bot','secret':'DROP'},
            'chat':{'id':123,'type':'private','title':'DROP'},
            'document':{'file_name':'result.html','file_size':1234,'file_id':'DROP'},'text':'DROP'},
            'token':'DROP','headers':{'Authorization':'DROP'},'url':'DROP'}
        expected={'http_status':200,'ok':True,'result':{'message_id':42,'date':1700000000,
            'from':{'id':99,'username':'fixture_bot'},'chat':{'id':123,'type':'private'},
            'document':{'file_name':'result.html','file_size':1234}}}
        self.assertEqual(response_excerpt(200,body),expected)
        self.assertTrue(delivery_result(200,body,'123',1,'fixture')['accepted'])
        minimal={'ok':True,'result':{'message_id':42,'chat':{'id':123}}}
        self.assertTrue(delivery_result(200,minimal,'123',1,'fixture')['accepted'])
        self.assertEqual(delivery_result(200,body,'456',1,'fixture')['status'],'UNKNOWN')
        for malformed in (None,[],{'ok':True,'result':[]},{'ok':True,'result':{'message_id':42,'chat':None}}):
            self.assertEqual(delivery_result(200,malformed,'123',1,'fixture')['status'],'UNKNOWN')

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
