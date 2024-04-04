from bs4 import BeautifulSoup
from telegram import Bot
import logging
import sqlite3
from sqlite3 import Error
from datetime import datetime
import requests
import json
import asyncio
import time


logging.basicConfig(level=logging.INFO)  

TELEGRAM_TOKEN = '' # TOKEN DO TELEGRAM QUE VOCÊ IRÁ ALOCAR O BOT.
TELEGRAM_CHAT_ID = '' # CHAT ID DO TELEGRAM QUE VOCÊ IRÁ ALOCAR O BOT.

async def send_to_telegram(message):
    bot = Bot(token=TELEGRAM_TOKEN)

    if len(message) <= 4096:  # 4096 é o comprimento máximo permitido pelo Telegram
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
    else:
        for chunk in [message[i:i + 4096] for i in range(0, len(message), 4096)]:
            await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=chunk)


async def process_page(url, headers, conn, cursor):
    try:
        html = requests.get(url=url, headers=headers, allow_redirects=True)
        html.raise_for_status()

        try:
            output = html.json()
        except json.decoder.JSONDecodeError as json_err:
            print(f"JSON Decode Error: {json_err}")
            print(f"Content: {html.text}")
            return  

        items_list = output.get('data', {}).get('products', {}).get('items', [])

        for item in items_list:
            name = item.get('name', '')
            url_key = item.get('url_key', '')
            pichau_prices = item.get('pichau_prices', {})
            avista_price = pichau_prices.get('avista', 'N/A')

            full_url = 'https://www.pichau.com.br/' + url_key

            # Verifica se o produto já está no banco de dados
            cursor.execute('SELECT preco_avista, preco_antigo FROM produtos WHERE nome = ? ORDER BY id DESC LIMIT 1', (name,))
            last_prices = cursor.fetchone()

            if last_prices:
                last_price, last_old_price = last_prices
                if last_price != avista_price:  # Verifica se o preço mudou
                    alert_message = f"Alerta! O produto {name} mudou. Novo preço: {avista_price}. Preço antigo: {last_price} - Link: {full_url}"
                    await send_to_telegram(alert_message)
                    print(alert_message)

                    # Atualiza o registro existente no banco de dados
                    try:
                        cursor.execute('UPDATE produtos SET preco_avista=?, preco_antigo=? WHERE nome=?',
                                    (avista_price, last_price, name))
                        conn.commit()
                    except Error as e:
                        print(f"Erro ao atualizar no banco de dados: {e}")
            else:
                # Produto não existe no banco de dados, insere como novo
                try:
                    cursor.execute('INSERT INTO produtos (nome, url, preco_avista, preco_antigo) VALUES (?, ?, ?, ?)',
                                (name, full_url, avista_price, avista_price))
                    conn.commit()
                except Error as e:
                    print(f"Erro ao inserir no banco de dados: {e}")

    except requests.exceptions.HTTPError as errh:
        print(f"HTTP Error: {errh}")
    except requests.exceptions.ConnectionError as errc:
        print(f"Error Connecting: {errc}")
    except requests.exceptions.Timeout as errt:
        print(f"Timeout Error: {errt}")
    except requests.exceptions.RequestException as err:
        print(f"Request Exception: {err}")

async def main():
    conn = sqlite3.connect('dados_produtos.db')
    cursor = conn.cursor()

    # Criação da tabela se ainda não existir
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT,
            url TEXT,
            preco_avista REAL,
            preco_antigo REAL
        )
    ''')
    conn.commit()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36'
    }

    pages = [
        #URL DE UMA PAGINA DE PLACA DE VIDEO. É POSSIVEL ADICIONAR QUANTAS PAGINAS E DE QUAIS PRODUTOS VOCÊ QUISER.
        'https://www.pichau.com.br/api/pichau?query=query%20category(%24id%3A%20Int!%2C%20%24pageSize%3A%20Int!%2C%20%24onServer%3A%20Boolean!%2C%20%24currentPage%3A%20Int!)%20%7B%0A%20%20category(id%3A%20%24id)%20%7B%0A%20%20%20%20id%0A%20%20%20%20description%0A%20%20%20%20name%0A%20%20%20%20product_count%0A%20%20%20%20url_key%0A%20%20%20%20search_filters_order%0A%20%20%20%20breadcrumbs%20%7B%0A%20%20%20%20%20%20category_id%0A%20%20%20%20%20%20category_name%0A%20%20%20%20%20%20category_level%0A%20%20%20%20%20%20category_url_key%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20pichau_faq%20%7B%0A%20%20%20%20%20%20answer%0A%20%20%20%20%20%20question%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20meta_title%20%40include(if%3A%20%24onServer)%0A%20%20%20%20meta_keywords%20%40include(if%3A%20%24onServer)%0A%20%20%20%20meta_description%20%40include(if%3A%20%24onServer)%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20products(%0A%20%20%20%20pageSize%3A%20%24pageSize%0A%20%20%20%20currentPage%3A%20%24currentPage%0A%20%20%20%20filter%3A%20%7Bcategory_id%3A%20%7Beq%3A%20%22309%22%7D%2C%20hide_from_search%3A%20%7Beq%3A%20%220%22%7D%7D%0A%20%20%20%20sort%3A%20%7Brelevance%3A%20DESC%7D%0A%20%20)%20%7B%0A%20%20%20%20aggregations%20%7B%0A%20%20%20%20%20%20count%0A%20%20%20%20%20%20label%0A%20%20%20%20%20%20attribute_code%0A%20%20%20%20%20%20options%20%7B%0A%20%20%20%20%20%20%20%20count%0A%20%20%20%20%20%20%20%20label%0A%20%20%20%20%20%20%20%20value%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20items%20%7B%0A%20%20%20%20%20%20id%0A%20%20%20%20%20%20sku%0A%20%20%20%20%20%20url_key%0A%20%20%20%20%20%20name%0A%20%20%20%20%20%20socket%0A%20%20%20%20%20%20hide_from_search%0A%20%20%20%20%20%20is_openbox%0A%20%20%20%20%20%20openbox_state%0A%20%20%20%20%20%20openbox_condition%0A%20%20%20%20%20%20tipo_de_memoria%0A%20%20%20%20%20%20caracteristicas%0A%20%20%20%20%20%20slots_memoria%0A%20%20%20%20%20%20marcas%0A%20%20%20%20%20%20marcas_info%20%7B%0A%20%20%20%20%20%20%20%20name%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20product_page_layout%0A%20%20%20%20%20%20formato_placa%0A%20%20%20%20%20%20plataforma%0A%20%20%20%20%20%20portas_sata%0A%20%20%20%20%20%20slot_cooler_120%0A%20%20%20%20%20%20slot_cooler_80%0A%20%20%20%20%20%20slot_cooler_140%0A%20%20%20%20%20%20slot_cooler_200%0A%20%20%20%20%20%20coolerbox_included%0A%20%20%20%20%20%20potencia%0A%20%20%20%20%20%20quantidade_pacote%0A%20%20%20%20%20%20alerta_monteseupc%0A%20%20%20%20%20%20vgaintegrado%0A%20%20%20%20%20%20product_set_name%0A%20%20%20%20%20%20categories%20%7B%0A%20%20%20%20%20%20%20%20name%0A%20%20%20%20%20%20%20%20url_path%0A%20%20%20%20%20%20%20%20path%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20special_price%0A%20%20%20%20%20%20pichau_prices%20%7B%0A%20%20%20%20%20%20%20%20avista%0A%20%20%20%20%20%20%20%20avista_discount%0A%20%20%20%20%20%20%20%20avista_method%0A%20%20%20%20%20%20%20%20base_price%0A%20%20%20%20%20%20%20%20final_price%0A%20%20%20%20%20%20%20%20max_installments%0A%20%20%20%20%20%20%20%20min_installment_price%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20price_range%20%7B%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20description%20%7B%0A%20%20%20%20%20%20%20%20html%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20garantia%0A%20%20%20%20%20%20informacoes_adicionais%0A%20%20%20%20%20%20image%20%7B%0A%20%20%20%20%20%20%20%20url%0A%20%20%20%20%20%20%20%20url_listing%0A%20%20%20%20%20%20%20%20path%0A%20%20%20%20%20%20%20%20label%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20media_gallery%20%7B%0A%20%20%20%20%20%20%20%20url%0A%20%20%20%20%20%20%20%20path%0A%20%20%20%20%20%20%20%20label%0A%20%20%20%20%20%20%20%20position%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20short_description%20%7B%0A%20%20%20%20%20%20%20%20html%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20amasty_label%20%7B%0A%20%20%20%20%20%20%20%20name%0A%20%20%20%20%20%20%20%20product_labels%20%7B%0A%20%20%20%20%20%20%20%20%20%20image%0A%20%20%20%20%20%20%20%20%20%20position%0A%20%20%20%20%20%20%20%20%20%20size%0A%20%20%20%20%20%20%20%20%20%20label%0A%20%20%20%20%20%20%20%20%20%20label_color%0A%20%20%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20%20%20category_labels%20%7B%0A%20%20%20%20%20%20%20%20%20%20image%0A%20%20%20%20%20%20%20%20%20%20position%0A%20%20%20%20%20%20%20%20%20%20size%0A%20%20%20%20%20%20%20%20%20%20label%0A%20%20%20%20%20%20%20%20%20%20label_color%0A%20%20%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20reviews%20%7B%0A%20%20%20%20%20%20%20%20rating%0A%20%20%20%20%20%20%20%20count%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20mysales_promotion%20%7B%0A%20%20%20%20%20%20%20%20expire_at%0A%20%20%20%20%20%20%20%20price_discount%0A%20%20%20%20%20%20%20%20price_promotional%0A%20%20%20%20%20%20%20%20promotion_name%0A%20%20%20%20%20%20%20%20promotion_url%0A%20%20%20%20%20%20%20%20qty_available%0A%20%20%20%20%20%20%20%20qty_sold%0A%20%20%20%20%20%20%20%20__typename%0A%20%20%20%20%20%20%7D%0A%20%20%20%20%20%20only_x_left_in_stock%0A%20%20%20%20%20%20stock_status%0A%20%20%20%20%20%20codigo_barra%0A%20%20%20%20%20%20codigo_ncm%0A%20%20%20%20%20%20meta_title%20%40include(if%3A%20%24onServer)%0A%20%20%20%20%20%20meta_keyword%20%40include(if%3A%20%24onServer)%0A%20%20%20%20%20%20meta_description%20%40include(if%3A%20%24onServer)%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20page_info%20%7B%0A%20%20%20%20%20%20total_pages%0A%20%20%20%20%20%20current_page%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20total_count%0A%20%20%20%20__typename%0A%20%20%7D%0A%20%20banners%3A%20rbsliderBanner(area%3A%20CATEGORY%2C%20categoryId%3A%20309)%20%7B%0A%20%20%20%20id%0A%20%20%20%20name%0A%20%20%20%20position%0A%20%20%20%20page_type%0A%20%20%20%20display_arrows%0A%20%20%20%20display_bullets%0A%20%20%20%20sliders%20%7B%0A%20%20%20%20%20%20id%0A%20%20%20%20%20%20url%0A%20%20%20%20%20%20is_add_nofollow_to_url%0A%20%20%20%20%20%20is_open_url_in_new_window%0A%20%20%20%20%20%20status%0A%20%20%20%20%20%20display_to%0A%20%20%20%20%20%20display_from%0A%20%20%20%20%20%20img_url_final%0A%20%20%20%20%20%20mobile_url_final%0A%20%20%20%20%20%20img_alt%0A%20%20%20%20%20%20img_url%0A%20%20%20%20%20%20img_type%0A%20%20%20%20%20%20img_title%0A%20%20%20%20%20%20__typename%0A%20%20%20%20%7D%0A%20%20%20%20__typename%0A%20%20%7D%0A%7D%0A&operationName=category&variables=%7B%22id%22%3A%22309%22%2C%22pageSize%22%3A36%2C%22currentPage%22%3A2%2C%22idString%22%3A%22309%22%2C%22facetsMainCategoryId%22%3A%22309%22%2C%22onServer%22%3Atrue%2C%22q%22%3Anull%7D',
    ]
    while True: 
        for page_url in pages:
            truncated_url = page_url[:30]  
            try:
                print(f"Iniciando verificação de página: {truncated_url}...")
                await process_page(page_url, headers, conn, cursor)
                print(f"Verificação concluída para página: {truncated_url}")
            except Exception as e:
                print(f"Erro: {truncated_url}, {e}")


        await asyncio.sleep(1)  # aguarda 1 segundo antes de começar a próxima iteração (ajuste como quiser)
        print("Todas as páginas foram verificadas")


if __name__ == "__main__":
    asyncio.run(main())



