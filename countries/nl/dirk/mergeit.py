import json

with open("JSONs/dirk_structured.json", "r", encoding="utf-8") as f1:
    data1 = json.load(f1)

with open("JSONs/dirk_actie_probeer_structured.json", "r", encoding="utf-8") as f2:
    data2= json.load(f2)

data3 = data1 + data2

with open("JSONs/final.json", "w", encoding="utf-8") as f3:
    json.dump(data3,f3,ensure_ascii=False,indent=2)
