import unittest
from page_text import extract_text

class TextTests(unittest.TestCase):
    def test_css_before_prose_cannot_consume_limit(self):
        body='<html><head><style>'+('@font-face{src:url(x)}'*4000)+'</style></head><body><main>Real eligibility &amp; onboarding. <a href="/rules">Rules</a>.</main></body></html>'
        result=extract_text(body)
        self.assertEqual(result['text'],'Real eligibility & onboarding. Rules .')
        self.assertFalse(result['truncated'])
        self.assertNotIn('font',result['text'])

    def test_hidden_script_template_and_svg_excluded(self):
        body='<body><script>steal()</script><template>bad</template><svg><text>bad</text></svg><div hidden><p>bad</p></div><p aria-hidden="true">bad</p><p>Useful body</p></body>'
        self.assertEqual(extract_text(body)['text'],'Useful body')

    def test_main_selected_and_limits_reported(self):
        result=extract_text('<nav>Menu</nav><main>ABCDE</main><footer>Footer</footer>',limit=3)
        self.assertEqual(result['text'],'ABC')
        self.assertEqual(result['extracted_characters'],5)
        self.assertTrue(result['truncated'])

    def test_self_closing_nodes_do_not_hide_later_content(self):
        self.assertEqual(extract_text('<div hidden/><p>A<br>B</p>')['text'],'A B')

if __name__=='__main__':unittest.main()
