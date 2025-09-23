import random

hexagrams = {
    "乾": "元亨利贞，君子以自强不息。",
    "坤": "厚德载物，君子以厚德载物。",
    # ... 可扩展六十四卦
}

def generate_hexagram():
    # 简化：随机返回一个卦
    return random.choice(list(hexagrams.items()))
