from flask import Flask, request, jsonify
import openai
import json
import re
import spacy
import numpy as np
from sklearn.neighbors import NearestNeighbors
from sklearn.metrics.pairwise import cosine_similarity
import time

app = Flask(__name__)
# 이 자리에 openai_key
nlp = spacy.load("en_core_web_md")

vegan_dict = {
    "strict": {"meat": -1, "fish": -1, "egg": -1, "dairy": -1, "vegetable": 1},
    "lacto": {"meat": -1, "fish": -1, "egg": -1, "dairy": 1, "vegetable": 1},
    "ovo": {"meat": -1, "fish": -1, "egg": 1, "dairy": -1, "vegetable": 1},
    "pescatarian": {"meat": -1, "fish": 1, "egg": 1, "dairy": 1, "vegetable": 1},
    "flexitarian": {"meat": 0.5, "fish": 0.5, "egg": 1, "dairy": 1, "vegetable": 1},
    "none": {"meat": 1, "fish": 1, "egg": 1, "dairy": 1, "vegetable": 1}
}

def get_spacy_similarity(word1, word2):
    vec1 = nlp(word1).vector
    vec2 = nlp(word2).vector
    return cosine_similarity([vec1], [vec2])[0][0]

def create_recipe_feature_vector(recipe, vegan_score, user_data):
    ingredients = [item["name"] for item in recipe["ingredients"]]

    meat_score = sum(get_spacy_similarity("meat", ing) * vegan_score["meat"] for ing in ingredients if get_spacy_similarity("meat", ing) > 0.3)
    fish_score = sum(get_spacy_similarity("fish", ing) * vegan_score["fish"] for ing in ingredients if get_spacy_similarity("fish", ing) > 0.3)
    egg_score = sum(get_spacy_similarity("egg", ing) * vegan_score["egg"] for ing in ingredients if get_spacy_similarity("egg", ing) > 0.3)
    dairy_score = sum(get_spacy_similarity("dairy", ing) * vegan_score["dairy"] for ing in ingredients if get_spacy_similarity("dairy", ing) > 0.3)
    vege_score = sum(get_spacy_similarity("vegetable", ing) * vegan_score["vegetable"] for ing in ingredients if get_spacy_similarity("vegetable", ing) > 0.3)

    penalty = min(meat_score + fish_score + egg_score + dairy_score, -5)
    reward = vege_score + 1 if vege_score > 2 else vege_score

    for allergic_food in user_data.get("allergies", []):
        for ingredient in ingredients:
            similarity = get_spacy_similarity(allergic_food, ingredient)
            if similarity > 0.15:
                penalty += -max(5, 10 * similarity)

    reward += 0.5 if abs(recipe.get("spice_level", 0) - user_data.get("spiciness", 0)) <= 1 else 0

    return [meat_score, fish_score, egg_score, dairy_score, vege_score, penalty, reward]

@app.route("/generate", methods=["POST"])
def generate():
    try:
        data = request.get_json()
        ingredients = data.get("userIngredients", [])
        user_data = data.get("userPreferences", {})
        vegan_score = vegan_dict.get(user_data.get("vegan", "none"), vegan_dict["none"])

        gen_start = time.perf_counter()

        prompt = f"""
        You have access to a list of ingredients currently available in a user's refrigerator.
        Available ingredients: {', '.join(ingredients)}

        Based on these ingredients, suggest **12 recipes** that can be made.

        ### Output Format (Valid JSON)
        [
            {{
                "name": "Recipe Name",
                "description": "Brief description",
                "nutrition": {{"calories": "", "protein": "", "carbs": "", "fat": "", "fiber": "", "sugar": "", "sodium": ""}},
                "ingredients": [{{"name": "ingredient", "quantity": "50g"}}],
                "steps": ["Step 1", "Step 2"],
                "spice_level": 2,
                "reference": "https://example.com"
            }}
        ]
        """

        response = openai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
        )

        result_text = response.choices[0].message.content
        result_text = re.sub(r"```json|```", "", result_text).strip()
        recipe_data = json.loads(result_text)

        gen_end = time.perf_counter()
        print(f"레시피 생성 실행 시간: {(gen_end - gen_start) * 1000:.0f}ms")

        filter_start = time.perf_counter()
        recipe_features = np.array([create_recipe_feature_vector(r, vegan_score, user_data) for r in recipe_data])
        user_vector = np.array([
            user_data.get("meatConsumption", 0),
            user_data.get("fishConsumption", 0),
            0, 0,
            user_data.get("vegeConsumption", 0),
            0, 0
        ]).reshape(1, -1)

        nn_model = NearestNeighbors(n_neighbors=len(recipe_features), metric='euclidean')
        nn_model.fit(recipe_features)

        distances, indices = nn_model.kneighbors(user_vector)
        max_distance = max(distances.flatten())
        scores = [(10 - (dist / max_distance) * 10) for dist in distances.flatten()]

        sorted_recipes = sorted(
            [{"recipe": recipe_data[i], "score": scores[idx]} for idx, i in enumerate(indices.flatten())],
            key=lambda x: x["score"], reverse=True
        )

        filter_end = time.perf_counter()
        print(f"레시피 필터링 실행 시간: {(filter_end - filter_start) * 1000:.0f}ms")
        print(f"총 소요 시간: {(filter_end - gen_start) * 1000:.0f}ms")

        result = [item["recipe"] for item in sorted_recipes]
        return jsonify(result)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001, debug=True)
