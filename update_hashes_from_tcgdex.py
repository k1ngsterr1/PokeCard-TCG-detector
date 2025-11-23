#!/usr/bin/env python3
"""
Скрипт для загрузки карт из TCGdex API и вычисления их хешей
Использует API для получения списка карт и их изображений
"""
import requests
import pandas as pd
import imagehash
from PIL import Image
from io import BytesIO
import time
import pickle
import os

# API endpoints
TCGDEX_API = "https://api.tcgdex.net/v2/en"

def get_all_sets():
    """Получаем список всех сетов из TCGdex"""
    print("📦 Fetching all sets from TCGdex...")
    response = requests.get(f"{TCGDEX_API}/sets")
    if response.status_code == 200:
        sets = response.json()
        print(f"✅ Found {len(sets)} sets")
        return sets
    else:
        print(f"❌ Failed to fetch sets: {response.status_code}")
        return []

def get_cards_from_set(set_id):
    """Получаем все карты из конкретного сета"""
    response = requests.get(f"{TCGDEX_API}/sets/{set_id}")
    if response.status_code == 200:
        set_data = response.json()
        return set_data.get('cards', [])
    return []

def compute_hashes_for_image(image_url, card_id=None):
    """Загружаем изображение и вычисляем хеши"""
    try:
        # Загружаем изображение
        response = requests.get(image_url, timeout=15)
        if response.status_code != 200:
            return None, f"HTTP {response.status_code}"
        
        img = Image.open(BytesIO(response.content))
        
        # Вычисляем хеши
        phash = imagehash.phash(img, 32, 8)
        dhash = imagehash.dhash(img, 32)
        whash = imagehash.whash(img, 32)
        chash = imagehash.colorhash(img)
        
        return {
            'perceptual': phash,
            'difference': dhash,
            'wavelet': whash,
            'color': chash
        }, None
    except requests.exceptions.Timeout:
        return None, "Timeout (>15s)"
    except requests.exceptions.RequestException as e:
        return None, f"Network error: {str(e)[:30]}"
    except Exception as e:
        return None, f"Error: {str(e)[:30]}"

def update_hash_database(batch_size=50, start_from=0, limit=None):
    """
    Обновляет базу хешей картами из TCGdex
    
    Args:
        batch_size: Количество карт для обработки за раз перед сохранением
        start_from: С какого сета начать (для продолжения прерванной загрузки)
        limit: Максимальное количество карт для обработки (None = все)
    """
    # Загружаем существующую базу
    if os.path.exists('card_hashes_32b.pickle'):
        print("📚 Loading existing hash database...")
        existing_df = pd.read_pickle('card_hashes_32b.pickle')
        existing_ids = set(existing_df['id'].values)
        print(f"✅ Loaded {len(existing_ids)} existing cards")
    else:
        print("🆕 Creating new hash database...")
        existing_df = pd.DataFrame(columns=['id', 'perceptual', 'difference', 'wavelet', 'color'])
        existing_ids = set()
    
    # Получаем все сеты
    all_sets = get_all_sets()
    
    if not all_sets:
        print("❌ No sets found. Exiting.")
        return
    
    # Сортируем сеты по дате (новые первые)
    all_sets = sorted(all_sets, key=lambda x: x.get('releaseDate', ''), reverse=True)
    
    new_hashes = []
    total_processed = 0
    total_added = 0
    total_skipped = 0
    
    print(f"\n🚀 Starting hash computation...")
    print(f"   Will process sets starting from index {start_from}")
    if limit:
        print(f"   Limit: {limit} cards")
    print()
    
    for set_idx, set_info in enumerate(all_sets[start_from:], start=start_from):
        set_id = set_info['id']
        set_name = set_info.get('name', set_id)
        
        print(f"\n📦 [{set_idx + 1}/{len(all_sets)}] Processing set: {set_name} ({set_id})")
        
        # Получаем карты из сета
        cards = get_cards_from_set(set_id)
        print(f"   Found {len(cards)} cards in set")
        
        for card_idx, card in enumerate(cards, 1):
            card_id = card.get('id')
            card_name = card.get('name', 'Unknown')
            
            # Проверяем лимит
            if limit and total_processed >= limit:
                print(f"\n✅ Reached limit of {limit} cards. Stopping.")
                break
            
            total_processed += 1
            
            # Пропускаем если карта уже есть
            if card_id in existing_ids:
                total_skipped += 1
                if card_idx % 10 == 0:
                    print(f"   [{card_idx}/{len(cards)}] Skipping existing cards... ({total_skipped} skipped)")
                continue
            
            # Получаем URL изображения (предпочитаем high quality)
            image_url = None
            if 'image' in card:
                # image может быть строкой или объектом
                if isinstance(card['image'], str):
                    image_url = card['image']
                elif isinstance(card['image'], dict):
                    image_url = card['image'].get('large') or card['image'].get('small')
            
            if not image_url:
                print(f"   ⚠️  [{card_idx}/{len(cards)}] {card_name} ({card_id}): No image URL")
                continue
            
            print(f"   🔄 [{card_idx}/{len(cards)}] {card_name} ({card_id})...", end=' ')
            
            # Вычисляем хеши
            hashes, error = compute_hashes_for_image(image_url, card_id)
            
            if hashes:
                new_hashes.append({
                    'id': card_id,
                    'perceptual': hashes['perceptual'],
                    'difference': hashes['difference'],
                    'wavelet': hashes['wavelet'],
                    'color': hashes['color']
                })
                total_added += 1
                print("✅")
            else:
                print(f"❌ ({error})")
            
            # Сохраняем батчами
            if len(new_hashes) >= batch_size:
                print(f"\n   💾 Saving batch of {len(new_hashes)} cards...")
                new_df = pd.DataFrame(new_hashes)
                updated_df = pd.concat([existing_df, new_df], ignore_index=True)
                updated_df.to_pickle('card_hashes_32b.pickle')
                
                # Обновляем существующие данные
                existing_df = updated_df
                existing_ids.update([h['id'] for h in new_hashes])
                new_hashes = []
                
                print(f"   ✅ Database now has {len(existing_df)} cards")
                print(f"   📊 Progress: {total_added} added, {total_skipped} skipped, {total_processed} processed")
            
            # Небольшая пауза чтобы не нагружать API
            time.sleep(0.1)
        
        # Проверяем лимит после сета
        if limit and total_processed >= limit:
            break
    
    # Сохраняем оставшиеся карты
    if new_hashes:
        print(f"\n💾 Saving final batch of {len(new_hashes)} cards...")
        new_df = pd.DataFrame(new_hashes)
        updated_df = pd.concat([existing_df, new_df], ignore_index=True)
        updated_df.to_pickle('card_hashes_32b.pickle')
        print(f"✅ Database now has {len(updated_df)} cards")
    
    # Также сохраняем в CSV для удобства
    if os.path.exists('card_hashes_32b.pickle'):
        print("\n💾 Saving CSV version...")
        df = pd.read_pickle('card_hashes_32b.pickle')
        
        # Конвертируем хеши в строки для CSV
        df_csv = df.copy()
        df_csv['perceptual'] = df_csv['perceptual'].astype(str)
        df_csv['difference'] = df_csv['difference'].astype(str)
        df_csv['wavelet'] = df_csv['wavelet'].astype(str)
        df_csv['color'] = df_csv['color'].astype(str)
        
        df_csv.to_csv('card_hashes_32b.csv', index=False)
        print(f"✅ CSV saved with {len(df_csv)} cards")
    
    print("\n" + "="*80)
    print("📊 FINAL STATISTICS:")
    print(f"   Total processed: {total_processed} cards")
    print(f"   Newly added: {total_added} cards")
    print(f"   Skipped (already exist): {total_skipped} cards")
    print(f"   Database total: {len(existing_df) + len(new_hashes)} cards")
    print("="*80)
    print("\n✅ Done!")

if __name__ == '__main__':
    import sys
    
    # Параметры из командной строки
    batch_size = 50
    start_from = 0
    limit = None
    
    if len(sys.argv) > 1:
        limit = int(sys.argv[1])
        print(f"📌 Processing limit: {limit} cards")
    
    if len(sys.argv) > 2:
        start_from = int(sys.argv[2])
        print(f"📌 Starting from set index: {start_from}")
    
    print("\n🎴 TCGdex Hash Database Updater")
    print("="*80)
    print("This script will download card images from TCGdex API")
    print("and compute perceptual hashes for visual matching.")
    print("="*80 + "\n")
    
    try:
        update_hash_database(batch_size=batch_size, start_from=start_from, limit=limit)
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrupted by user. Progress has been saved.")
        print("You can resume by running the script again with the appropriate start_from parameter.")
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
