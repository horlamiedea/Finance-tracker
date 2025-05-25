from openai import OpenAI

class AIService:
    def __init__(self, api_key):
        self.client = OpenAI(api_key=api_key)

    def categorize_expenses(self, items_list):
        prompt = f"Categorize these expenses: {items_list}"
        response = self.client.completions.create(
            model="gpt-4o",
            prompt=prompt,
            max_tokens=150,
            temperature=0.3
        )
        return response.choices[0].text.strip()
