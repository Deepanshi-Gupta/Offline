from transformers import AutoTokenizer, AutoModelForSeq2SeqLM

MODEL_NAME = "facebook/nllb-200-distilled-600M"
'''
print("Downloading tokenizer...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

print("Downloading model...")
model = AutoModelForSeq2SeqLM.from_pretrained(MODEL_NAME)
'''
tokenizer = AutoTokenizer.from_pretrained("./models/nllb")
model = AutoModelForSeq2SeqLM.from_pretrained("./models/nllb")