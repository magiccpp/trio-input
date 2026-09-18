"""Write proto/truecase.json: words whose correct spelling is not lowercase.
"en"  = only when the candidate is English (Swedish writes måndag, svenska, i ... in lowercase)
"any" = names, brands and acronyms, whatever the language.
Ambiguous words (may, march, us, it, turkey, polish, apple, windows) are left out on purpose;
the user's own picks are learned by the app and take precedence.
"""
import json
from pathlib import Path

EN = """i:I i'm:I'm i'll:I'll i've:I've i'd:I'd
monday tuesday wednesday thursday friday saturday sunday
january february april june july august september october november december
english swedish chinese german french spanish italian japanese korean russian finnish norwegian danish dutch
american european asian african british swede swedes christmas easter mr:Mr mrs:Mrs ms:Ms dr:Dr"""

ANY = """sweden china america england germany france spain italy japan korea russia finland norway denmark
europe asia africa india canada australia brazil mexico poland ukraine netherlands switzerland austria
stockholm gothenburg:Gothenburg göteborg:Göteborg malmö:Malmö uppsala beijing shanghai shenzhen guangzhou hangzhou
london paris berlin tokyo madrid rome moscow helsinki oslo copenhagen amsterdam
sverige kina tyskland frankrike spanien italien danmark norge england usa:USA uk:UK eu:EU 
nvidia:NVIDIA amd:AMD intel ibm:IBM microsoft google amazon facebook openai:OpenAI anthropic claude
chatgpt:ChatGPT gpt:GPT github:GitHub gitlab:GitLab linux ubuntu debian android ios:iOS macos:macOS iphone:iPhone ipad:iPad
youtube:YouTube linkedin:LinkedIn whatsapp:WhatsApp wechat:WeChat tiktok:TikTok twitter instagram spotify netflix tesla
ericsson volvo ikea:IKEA saab huawei xiaomi alibaba tencent baidu samsung sony toyota bmw:BMW
python java javascript:JavaScript typescript:TypeScript pytorch:PyTorch tensorflow:TensorFlow cuda:CUDA openvino:OpenVINO
ai:AI llm:LLM gpu:GPU cpu:CPU npu:NPU igpu:iGPU vram:VRAM ssd:SSD usb:USB wifi:WiFi api:API sdk:SDK
ui:UI ux:UX pc:PC tv:TV pdf:PDF html:HTML css:CSS json:JSON sql:SQL http:HTTP https:HTTPS
url:URL ip:IP dns:DNS vpn:VPN ssh:SSH ceo:CEO cto:CTO hr:HR phd:PhD ime:IME"""


def parse(block):
    out = {}
    for tok in block.split():
        k, _, v = tok.partition(":")
        out[k] = v or k[:1].upper() + k[1:]
    return {k: v for k, v in out.items() if k != v}


out = {"en": parse(EN), "any": parse(ANY)}
p = Path(__file__).resolve().parent.parent / "proto" / "truecase.json"
p.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
print(len(out["en"]), "en +", len(out["any"]), "any ->", p)
