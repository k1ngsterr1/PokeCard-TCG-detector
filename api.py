"""
Simple REST API for Pokemon card image matching
Based on PokeCard-TCG-detector by em4go
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
import imagehash
from PIL import Image
import pandas as pd
import io
import base64

app = Flask(__name__)
CORS(app)  # Enable CORS for cross-origin requests

# Load pre-computed card hashes
print("Loading card hashes...")
card_hashes = pd.read_pickle("card_hashes_32b.pickle")
print(f"Loaded {len(card_hashes)} card hashes")


def get_hashes(img):
    """Calculate various types of hashes for an image."""
    perceptual = imagehash.phash(img, 32, 8)
    difference = imagehash.dhash(img, 32)
    wavelet = imagehash.whash(img, 32)
    color = imagehash.colorhash(img)
    return {
        "perceptual": perceptual,
        "difference": difference,
        "wavelet": wavelet,
        "color": color,
    }


def get_most_similar(img, hash_type="perceptual", n=5):
    """
    Find the most similar Pokémon cards based on image hash.
    
    Args:
        img: PIL Image object
        hash_type: Type of hash to use (perceptual, difference, wavelet, color)
        n: Number of similar cards to retrieve
        
    Returns:
        list: List of dicts with id, distance for top N matches
    """
    hashes_dict = get_hashes(img)
    card_hashes["distance"] = card_hashes[hash_type] - hashes_dict[hash_type]
    card_hashes["distance"] = card_hashes["distance"].astype("int")
    
    min_rows = card_hashes["distance"].nsmallest(n).index
    results = []
    
    for idx in min_rows:
        results.append({
            "id": card_hashes.loc[idx, "id"],
            "distance": int(card_hashes.loc[idx, "distance"])
        })
    
    return results


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({"status": "ok", "cards": len(card_hashes)})


@app.route("/match", methods=["POST"])
def match_card():
    """
    Match a Pokemon card from image data.
    
    Request body:
        {
            "image": "base64_encoded_image_data",
            "hash_type": "perceptual" (optional, default: perceptual),
            "top_n": 5 (optional, default: 5)
        }
        
    Response:
        {
            "success": true,
            "matches": [
                {"id": "base1-4", "distance": 0},
                {"id": "base1-58", "distance": 3},
                ...
            ]
        }
    """
    try:
        data = request.get_json()
        
        if not data or "image" not in data:
            return jsonify({"success": False, "error": "Missing image data"}), 400
        
        # Decode base64 image
        image_data = base64.b64decode(data["image"])
        img = Image.open(io.BytesIO(image_data))
        
        # Get parameters
        hash_type = data.get("hash_type", "perceptual")
        top_n = data.get("top_n", 5)
        
        # Find matches
        matches = get_most_similar(img, hash_type=hash_type, n=top_n)
        
        return jsonify({
            "success": True,
            "matches": matches,
            "hash_type": hash_type
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/match_file", methods=["POST"])
def match_card_file():
    """
    Match a Pokemon card from uploaded file.
    
    Form data:
        file: Image file (jpeg, png, etc.)
        hash_type: optional (default: perceptual)
        top_n: optional (default: 5)
    """
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400
        
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "error": "Empty filename"}), 400
        
        # Open image
        img = Image.open(file.stream)
        
        # Get parameters
        hash_type = request.form.get("hash_type", "perceptual")
        top_n = int(request.form.get("top_n", 5))
        
        # Find matches
        matches = get_most_similar(img, hash_type=hash_type, n=top_n)
        
        return jsonify({
            "success": True,
            "matches": matches,
            "hash_type": hash_type
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/compute_hash", methods=["POST"])
def compute_hash():
    """
    Compute hashes for a new card image.
    
    Request body:
        {
            "image": "base64_encoded_image_data",
            "card_id": "swsh4-81" (optional)
        }
        
    Response:
        {
            "success": true,
            "hashes": {
                "perceptual": "...",
                "difference": "...",
                "wavelet": "...",
                "color": "..."
            },
            "card_id": "swsh4-81"
        }
    """
    try:
        data = request.get_json()
        
        if not data or "image" not in data:
            return jsonify({"success": False, "error": "Missing image data"}), 400
        
        # Decode base64 image
        image_data = base64.b64decode(data["image"])
        img = Image.open(io.BytesIO(image_data))
        
        # Compute all hashes
        hashes = get_hashes(img)
        
        # Convert to strings for JSON
        hashes_str = {
            "perceptual": str(hashes["perceptual"]),
            "difference": str(hashes["difference"]),
            "wavelet": str(hashes["wavelet"]),
            "color": str(hashes["color"])
        }
        
        card_id = data.get("card_id")
        
        return jsonify({
            "success": True,
            "hashes": hashes_str,
            "card_id": card_id
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/add_card", methods=["POST"])
def add_card():
    """
    Add a new card hash to the database.
    
    Request body:
        {
            "image": "base64_encoded_image_data",
            "card_id": "swsh4-81"
        }
        
    Response:
        {
            "success": true,
            "card_id": "swsh4-81",
            "hashes": {...}
        }
    """
    global card_hashes
    
    try:
        data = request.get_json()
        
        if not data or "image" not in data or "card_id" not in data:
            return jsonify({"success": False, "error": "Missing image or card_id"}), 400
        
        card_id = data["card_id"]
        
        # Check if card already exists
        if card_id in card_hashes["id"].values:
            return jsonify({
                "success": False, 
                "error": f"Card {card_id} already exists in database"
            }), 400
        
        # Decode base64 image
        image_data = base64.b64decode(data["image"])
        img = Image.open(io.BytesIO(image_data))
        
        # Compute all hashes
        hashes = get_hashes(img)
        
        # Add to dataframe
        new_row = {
            "id": card_id,
            "perceptual": hashes["perceptual"],
            "difference": hashes["difference"],
            "wavelet": hashes["wavelet"],
            "color": hashes["color"]
        }
        
        card_hashes = pd.concat([card_hashes, pd.DataFrame([new_row])], ignore_index=True)
        
        # Save to pickle
        card_hashes.to_pickle("card_hashes_32b.pickle")
        
        print(f"✅ Added new card: {card_id} (total: {len(card_hashes)})")
        
        return jsonify({
            "success": True,
            "card_id": card_id,
            "hashes": {
                "perceptual": str(hashes["perceptual"]),
                "difference": str(hashes["difference"]),
                "wavelet": str(hashes["wavelet"]),
                "color": str(hashes["color"])
            },
            "total_cards": len(card_hashes)
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@app.route("/recognize", methods=["POST"])
def recognize_card():
    """
    Recognize a Pokemon card and return full details.
    
    Request body:
        {
            "image": "base64_encoded_image_data",
            "hash_type": "perceptual" (optional),
            "threshold": 30 (optional, max distance for match)
        }
        
    Response:
        {
            "success": true,
            "result": {
                "cardId": "base4-1",
                "cardName": "Alakazam",
                "confidence": 100.0,
                "method": "image-hash",
                "distance": 0,
                "imageUrl": "https://images.pokemontcg.io/base4/1_hires.png"
            }
        }
    """
    try:
        data = request.get_json()
        
        if not data or "image" not in data:
            return jsonify({"success": False, "error": "Missing image data"}), 400
        
        # Decode base64 image
        image_data = base64.b64decode(data["image"])
        img = Image.open(io.BytesIO(image_data))
        
        # Get parameters
        hash_type = data.get("hash_type", "perceptual")
        threshold = data.get("threshold", 30)
        
        # Find matches
        matches = get_most_similar(img, hash_type=hash_type, n=10)
        
        if not matches or len(matches) == 0:
            return jsonify({
                "success": False,
                "error": "No matches found"
            }), 404
        
        best_match = matches[0]
        
        # Check if match is good enough
        if best_match["distance"] > threshold:
            return jsonify({
                "success": False,
                "error": f"No good match found (best distance: {best_match['distance']})",
                "best_match": best_match
            }), 404
        
        # Calculate confidence (distance 0 = 100%, distance 30 = 50%)
        confidence = max(50, min(100, 100 - (best_match["distance"] / 3)))
        
        # Parse card ID to generate image URL
        card_id = best_match["id"]
        
        # Try to determine the image URL based on card ID format
        # Format examples: base4-1, swsh4-81, sv09-142
        if "-" in card_id:
            parts = card_id.split("-")
            set_id = parts[0]
            card_num = parts[1]
            
            # Check if it's a modern set (starts with sv, swsh, xy, sm, etc.)
            if set_id.startswith(("sv", "swsh", "sm", "xy")):
                # TCGdex format
                image_url = f"https://assets.tcgdex.net/en/{set_id}/{card_num}/high.png"
            else:
                # Pokemon TCG IO format (older sets)
                image_url = f"https://images.pokemontcg.io/{set_id}/{card_num}_hires.png"
        else:
            # Fallback
            image_url = f"https://assets.tcgdex.net/en/{card_id}/high.png"
        
        # Build result
        result = {
            "cardId": card_id,
            "cardName": card_id.split("-")[0].capitalize(),  # Fallback name
            "confidence": round(confidence, 1),
            "method": "image-hash",
            "distance": best_match["distance"],
            "imageUrl": image_url,
            "matches": matches[:5]  # Include top 5 matches for reference
        }
        
        return jsonify({
            "success": True,
            "result": result
        })
        
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    print("Starting Pokemon Card Image Matching API...")
    print("Endpoints:")
    print("  GET  /health - Health check")
    print("  POST /match - Match card from base64 image")
    print("  POST /match_file - Match card from uploaded file")
    print("  POST /compute_hash - Compute hashes for a card")
    print("  POST /add_card - Add a new card to the database")
    print("  POST /recognize - Recognize card and return full details")
    app.run(host="0.0.0.0", port=5001, debug=True)
