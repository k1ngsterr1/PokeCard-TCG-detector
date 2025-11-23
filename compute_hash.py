#!/usr/bin/env python3
"""
Скрипт для вычисления perceptual hash одной карты
Использование: python compute_hash.py <image_path>
"""
import sys
from PIL import Image
import imagehash

def compute_card_hash(image_path):
    """Вычисляет все 4 типа хешей для карты"""
    try:
        img = Image.open(image_path)
        
        # Вычисляем 4 типа хешей (как в PokeCard-TCG-detector)
        phash = str(imagehash.phash(img, hash_size=16))  # perceptual hash
        dhash = str(imagehash.dhash(img, hash_size=16))  # difference hash
        whash = str(imagehash.whash(img, hash_size=16))  # wavelet hash
        chash = str(imagehash.colorhash(img, binbits=8)) # color hash
        
        return {
            'perceptual': phash,
            'difference': dhash,
            'wavelet': whash,
            'color': chash
        }
    except Exception as e:
        print(f"Error computing hash: {e}", file=sys.stderr)
        return None

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python compute_hash.py <image_path>", file=sys.stderr)
        sys.exit(1)
    
    image_path = sys.argv[1]
    hashes = compute_card_hash(image_path)
    
    if hashes:
        # Выводим в формате JSON для легкого парсинга
        import json
        print(json.dumps(hashes))
    else:
        sys.exit(1)
