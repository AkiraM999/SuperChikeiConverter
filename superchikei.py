import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import base64
import os
from datetime import datetime, timedelta, timezone

# ページ設定
st.set_page_config(page_title="GPX to QGIS Database", layout="wide")
st.title("📍 調査用GPXデータ 変換ツール(β版)")

# ==========================================
# 画像を表に埋め込むための関数
# ==========================================
def get_image_tag(file_path):
    # 画像ファイルが存在すればBase64に変換してimgタグを作成、なければ空文字を返す
    if os.path.exists(file_path):
        with open(file_path, "rb") as f:
            data = base64.b64encode(f.read()).decode("utf-8")
        return f'<img src="data:image/png;base64,{data}" width="40">'
    return ""

img_03 = get_image_tag("green_pin.png")
img_04 = get_image_tag("orange_pin.png")
img_05 = get_image_tag("pink_pin.png")
img_06 = get_image_tag("yellow_pin.png")

# ＝=========================================
# アプリの説明書き（UI部分）
# ==========================================
st.markdown("""
### 📝 アプリの仕様
* **時間の変換**: GPXに記録されている時刻(UTC)は、自動的に**日本標準時(JST)**に変換され、「日付」と「時刻」の別々の列に出力されます。
* **フラグの自動判定**: 
  * 「読み」や「コメント」に **`sample`** と記載されている場合は、`Sample_Flag` が `True`（チェックあり）になります。
  * 「読み」や「コメント」に **`帯磁率`** と記載されている場合は、`Magne_Flag` が `True` になります。
""")

st.markdown("### 📌 現在対応しているアイコンと岩相の対応表")

# HTMLのimgタグをMarkdownの表に埋め込む（unsafe_allow_html=Trueが必須）
st.markdown(f"""
| アイコン | アイコン番号 | 判定される岩相・状態 | 備考 |
| :---: | :--- | :--- | :--- |
| {img_03} | **1700003** | mdst | |
| {img_04} | **1700004** | alt. mdst sst | |
| {img_05} | **1700005** | tf | |
| {img_06} | **1700006** | sst | |
| 🚫 | **1910003** | Road Closed (通行止め) | 別列で `True` になります |
""", unsafe_allow_html=True)

st.divider() # 区切り線

# ==========================================
# 処理ロジック
# ==========================================
LITHOLOGY_MAPPING = {
    "1700003": "mdst",
    "1700004": "alt. mdst sst",
    "1700005": "tf",
    "1700006": "sst"
}
ROAD_CLOSED_ICON = "1910003"

def process_gpx(file_content):
    ns = {
        'default': 'http://www.topografix.com/GPX/1/1',
        'kashmir3d': 'http://www.kashmir3d.com/namespace/kashmir3d'
    }
    
    content_str = file_content.decode('utf-8', errors='replace')
    tree = ET.parse(io.StringIO(content_str))
    root = tree.getroot()
    
    data_list = []
    jst_tz = timezone(timedelta(hours=9), 'JST')
    
    for wpt in root.findall('default:wpt', ns):
        lat = wpt.get('lat')
        lon = wpt.get('lon')
        
        ele = wpt.find('default:ele', ns).text if wpt.find('default:ele', ns) is not None else ""
        name = wpt.find('default:name', ns).text if wpt.find('default:name', ns) is not None else ""
        cmt = wpt.find('default:cmt', ns).text if wpt.find('default:cmt', ns) is not None else ""
        
        time_str = wpt.find('default:time', ns).text if wpt.find('default:time', ns) is not None else ""
        date_val = ""
        time_val = ""
        
        if time_str:
            try:
                dt_utc = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
                dt_jst = dt_utc.astimezone(jst_tz)
                date_val = dt_jst.strftime('%Y-%m-%d')
                time_val = dt_jst.strftime('%H:%M:%S')
            except ValueError:
                date_val = time_str
        
        extensions = wpt.find('default:extensions', ns)
        icon_num = ""
        yomi = ""
        
        if extensions is not None:
            icon_elem = extensions.find('kashmir3d:icon', ns)
            if icon_elem is not None:
                icon_num = icon_elem.text
                
            yomi_elem = extensions.find('kashmir3d:yomi', ns)
            if yomi_elem is not None and yomi_elem.text is not None:
                yomi = yomi_elem.text

        photo_dict = {}
        links = wpt.findall('default:link', ns)
        for i, link in enumerate(links, start=1):
            href = link.get('href')
            if href:
                photo_dict[f'Photo_{i}'] = href

        lithology = LITHOLOGY_MAPPING.get(icon_num, "") 
        road_closed_flag = True if icon_num == ROAD_CLOSED_ICON else False
        
        text_lower = f"{yomi} {cmt}".lower()
        text_raw = f"{yomi} {cmt}"
        
        sample_flag = True if "sample" in text_lower else False
        magne_flag = True if "帯磁率" in text_raw else False

        row_data = {
            'Point_Name': name,
            'Latitude': lat,
            'Longitude': lon,
            'Elevation': ele,
            'Date': date_val,
            'Time': time_val,
            'Lithology': lithology,
            'Sample_Flag': sample_flag,
            'Magne_Flag': magne_flag,
            'Road_Closed': road_closed_flag,
            'Comment': cmt,
            'Yomi': yomi,
            'Icon_Num': icon_num
        }
        
        row_data.update(photo_dict)
        data_list.append(row_data)
        
    return pd.DataFrame(data_list)

# ==========================================
# ファイルアップロード部
# ==========================================
uploaded_file = st.file_uploader("📂 GPXファイルをアップロードしてください", type=["gpx"])

if uploaded_file is not None:
    with st.spinner('データを変換中...'):
        file_content = uploaded_file.read()
        df = process_gpx(file_content)
    
    st.success("✅ 変換が完了しました！")
    
    df = df.fillna("")
    st.dataframe(df, use_container_width=True)
    
    st.markdown("### 💾 ダウンロード設定")
    encoding_choice = st.radio(
        "CSVの文字コードを選んでください（文字化けする場合は変更してください）",
        ("UTF-8 (BOM付き) - 多くの環境で推奨", "Shift-JIS - WindowsのExcelで直接開く場合", "UTF-8 - QGIS等の標準")
    )
    
    if "Shift-JIS" in encoding_choice:
        enc = 'shift_jis'
        csv = df.to_csv(index=False, encoding=enc, errors='ignore')
    elif "BOM付き" in encoding_choice:
        enc = 'utf-8-sig'
        csv = df.to_csv(index=False, encoding=enc)
    else:
        enc = 'utf-8'
        csv = df.to_csv(index=False, encoding=enc)

    st.download_button(
        label=f"📥 CSVをダウンロード ({enc})",
        data=csv,
        file_name="geology_data.csv",
        mime="text/csv",
    )