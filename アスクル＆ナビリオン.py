import streamlit as st
import requests
from bs4 import BeautifulSoup
import re
import pandas as pd
import time

# 商品情報を取得する関数 (アスクルページから)
def get_askul_product_info(url):
    headers = {"User-Agent": "Mozilla/5.0"}
    res = requests.get(url, headers=headers)
    time.sleep(0.5) # アスクルへの接続後に遅延
    soup = BeautifulSoup(res.text, "html.parser")

    # 商品名（titleタグから取得し、「 - アスクル」を除去）
    if res.status_code != 200:
        name = ""
    elif soup.title:
        name = soup.title.string.strip()
        if name == "Not Found":
            name = ""
        elif name.endswith(" - アスクル"):
            name = name.removesuffix(" - アスクル")
    else:
        name = ""

    # 値段
    price = ""
    price_tag = soup.find("span", class_="item-price-value")
    if not price_tag:
        price_tag = soup.find("span", class_="item-price-taxin")
    if price_tag:
        price = price_tag.get_text(strip=True)
    else:
        price_candidates = soup.find_all(string=re.compile("￥"))
        for candidate in price_candidates:
            text = candidate.strip()
            if re.match(r"^￥[0-9,]+", text):
                price = text
                break
    if not price:
        price = ""

    # 販売単位
    quantity = ""
    for tag in soup.find_all(string=re.compile("販売単位")): # type: ignore
        quantity = tag.strip()
        break
    if not quantity:
        quantity = ""

    # 「販売単位：」の文字列を除去
    quantity = quantity.replace("販売単位：", "").strip()

    # JANコード
    jan = ""
    for tag in soup.find_all(string=re.compile("JANコード")): # type: ignore
        m = re.search(r"JANコード[:：]?\s*([0-9]+)", tag)
        if m:
            jan = f"JANコード：{m.group(1)}"
        else:
            jan = tag.strip()
        break
    if not jan:
        jan = ""
    jan_code = jan.replace("JANコード：", "").strip()

    return {
        "アスクル品名": name,
        "個数": quantity,
        "JANコード": jan_code,
        "値段": price,
        "URL": url,
    }

# NTPS-shopの商品URLをJANコードから取得する関数
def get_product_urls_from_jan(session, jan_code):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    session.headers.update(headers)
    # まずトップページにアクセス
    top_url = "https://www.ntps-shop.com/shop/wellstech/"
    try:
        session.get(top_url)
        time.sleep(0.5) # NTPS-shop トップページへの接続後に遅延
    except requests.exceptions.RequestException:
        return [] # エラー時は空リストを返す

    # その後、検索ページにアクセス
    search_url = f"https://www.ntps-shop.com/search/res/{jan_code}/"
    try:
        response = session.get(search_url)
        time.sleep(0.5) # NTPS-shop 検索ページへの接続後に遅延
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'lxml')
    except requests.exceptions.RequestException:
        return [] # エラー時は空リストを返す


    # 1. 個数ごとのリンクを一番上のみ取得
    links = soup.select('td.tano-center a[href*="/product/"]')
    product_urls = []
    if links:
        a_tag = links[0]
        href = a_tag['href']
        m = re.search(r'(/product/\d+/)', href)
        if m:
            relative_url = m.group(1)
            product_urls.append(f"https://www.ntps-shop.com{relative_url}")
    # 2. なければ従来通りのリンクを1件取得
    if not product_urls:
        a_tag = soup.select_one('div.tano-item-detail-right a.tano-item-name')
        if a_tag and a_tag.has_attr('href'):
            href = a_tag['href']
            m = re.search(r'(/product/\d+/)', href)
            if m:
                relative_url = m.group(1)
                product_urls.append(f"https://www.ntps-shop.com{relative_url}")

    return product_urls  # 0件なら空リスト

# NTPS-shopの商品情報を商品コードから取得する関数
def get_giftechs_product_info(session, product_code):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    session.headers.update(headers)


    # 2. 商品ページにアクセス
    product_url = f"https://www.ntps-shop.com/product/{product_code}/"
    try:
        response = session.get(product_url)
        time.sleep(0.5) # NTPS-shop 商品ページへの接続後に遅延
        response.encoding = response.apparent_encoding
        soup = BeautifulSoup(response.text, 'lxml')
    except requests.exceptions.RequestException:
        return {} # エラー時は空辞書を返す


    # 3. 必要な情報をBeautifulSoupのCSSセレクタで取得
    product_name_element = soup.select_one('h1#tano-h1 > span, h1.tano-h1-type-01 > span, section.entry-content h1 > span')
    product_name = product_name_element.get_text(strip=True) if product_name_element else ""

    price_element = soup.select_one('span#tano-sale-price > span')
    price = price_element.get_text(strip=True) if price_element else ""

    # まず、該当のdl要素を取得
    dl = soup.select_one('dl.tano-product-stock-left')

    unit = ""
    if dl:
        # dtタグで「販売単位」となっているものを探す
        dt = dl.find('dt', string="販売単位")
        if dt:
            # その直後のddタグを取得
            dd = dt.find_next_sibling('dd')
            if dd:
                unit = dd.get_text(strip=True)

    product_name = re.sub(r'[\u3000\s]+', ' ', product_name).strip()

    return {
        "製品": product_name,
        "NV小売価格": price,
        "個数_シート": unit,
        "申し込み番号": product_code
    }


st.title("アスクル商品情報取得ツール")
st.write("商品番号またはURLを1行ずつ入力してください。商品番号のみでもOKです。")

input_text = st.text_area("商品番号またはURL（1行に1つ）", height=200)

if st.button("情報取得"):
    lines = [line.strip() for line in input_text.splitlines() if line.strip()]
    urls = []
    for line in lines:
        if line.startswith("http"):
            urls.append(line)
        else:
            # 商品番号のみの場合
            urls.append(f"https://www.askul.co.jp/p/{line}/")

    results = []
    progress = st.progress(0)
    
    # セッションをここで一度作成し、各商品情報の取得に使い回す
    ntps_session = requests.Session()

    for i, url in enumerate(urls):
        askul_info = get_askul_product_info(url)
        jan_code = askul_info.get("JANコード", "")
        
        giftechs_info = {
             "同一商品判定": "該当商品なし",
             "製品": "",
             "個数_シート": "",
             "申し込み番号": "",
             "NV小売価格": "",
             "URL_シート": ""
        }

        if jan_code:
            # セッションを渡して呼び出す
            product_urls = get_product_urls_from_jan(ntps_session, jan_code)
            if product_urls:
                 # 最初のURLを使う
                giftechs_url = product_urls[0]
                m = re.search(r'/product/(\d+)/', giftechs_url)
                if m:
                    product_code = m.group(1)
                    # セッションを渡して呼び出す
                    giftechs_data = get_giftechs_product_info(ntps_session, product_code)
                    if giftechs_data:
                         giftechs_info = {
                             "同一商品判定": "同一商品",
                             "製品": giftechs_data.get("製品", ""),
                             "個数_シート": giftechs_data.get("個数_シート", ""),
                             "申し込み番号": giftechs_data.get("申し込み番号", ""),
                             "NV小売価格": giftechs_data.get("NV小売価格", ""),
                             "URL_シート": giftechs_url
                         }
                    else:
                         giftechs_info["同一商品判定"] = "情報取得失敗"
                else:
                     giftechs_info["同一商品判定"] = "URLパターン不一致"
            else:
                 giftechs_info["同一商品判定"] = "類似商品"
                 giftechs_info["URL_シート"] = f"https://www.ntps-shop.com/search/res/{jan_code}/"
        else:
             giftechs_info["同一商品判定"] = ""
             giftechs_info["URL_シート"] = ""

        combined_info = {**askul_info, **giftechs_info}
        results.append(combined_info)

        # プログレスバーと同時に現在の処理数を表示
        progress.progress((i + 1) / len(urls), text=f"処理中: {i + 1} / {len(urls)}")
        time.sleep(0.5)
        
    progress.empty()
    df = pd.DataFrame(results)
    st.dataframe(df)
