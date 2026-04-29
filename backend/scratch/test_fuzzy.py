from rapidfuzz import fuzz, process

choices = ["Strongly Agree", "Agree", "Disagree", "Strongly Disagree"]
query = "5tr0ng!y Agre"

print("ratio:", process.extractOne(query, choices, scorer=fuzz.ratio))
print("token_set_ratio:", process.extractOne(query, choices, scorer=fuzz.token_set_ratio))
print("token_sort_ratio:", process.extractOne(query, choices, scorer=fuzz.token_sort_ratio))
print("partial_ratio:", process.extractOne(query, choices, scorer=fuzz.partial_ratio))
print("WRatio:", process.extractOne(query, choices, scorer=fuzz.WRatio))
print("QRatio:", process.extractOne(query, choices, scorer=fuzz.QRatio))
