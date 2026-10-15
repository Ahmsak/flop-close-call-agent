"""Extract document prose before truncation; never execute HTML or CSS."""
from html.parser import HTMLParser

class DocumentText(HTMLParser):
    SKIP = {'script','style','template','noscript','svg','head'}
    VOID = {'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack=[]; self.parts=[]; self.main=[]; self.has_main=False

    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        blocked=(tag in self.SKIP or 'hidden' in attrs or attrs.get('aria-hidden')=='true' or
                 any(item[1] for item in self.stack))
        main=tag in ('main','article') or any(item[2] for item in self.stack)
        if main and not blocked: self.has_main=True
        if tag not in self.VOID: self.stack.append((tag,blocked,main))
        self.parts.append(' '); self.main.append(' ')

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in self.VOID: self.handle_endtag(tag)

    def handle_endtag(self, tag):
        for i in range(len(self.stack)-1,-1,-1):
            if self.stack[i][0]==tag:
                del self.stack[i:]; break
        self.parts.append(' '); self.main.append(' ')

    def handle_data(self, data):
        if not any(item[1] for item in self.stack):
            self.parts.append(data)
            if any(item[2] for item in self.stack): self.main.append(data)

def extract_text(body, limit=24000):
    parser=DocumentText(); parser.feed(body); parser.close()
    text=' '.join(''.join(parser.main if parser.has_main else parser.parts).split())
    return {'text':text[:limit], 'extracted_characters':len(text), 'truncated':len(text)>limit,
            'extractor':'document-prose-v1', 'region':'main/article' if parser.has_main else 'body'}
