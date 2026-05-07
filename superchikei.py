import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io
import base64
import os
from datetime import datetime, timedelta, timezone
from pyproj import Transformer

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
img_07 = get_image_tag("road_closed.png")

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
| {img_07} | **1910003** | Road Closed (通行止め) | 別列で `True` になります |
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

# 座標変換関数
def add_xy_coordinates(df, coord_sys):
    if coord_sys == "選択しない":
        return df
    
    # JGD2011の各系のEPSGコード
    if coord_sys == "平面直角座標系Ⅷ（８）系":
        epsg = 6676
    elif coord_sys == "平面直角座標系Ⅹ（１０）系":
        epsg = 6678
    else:
        return df

    # WGS84(EPSG:4326) から 目的の平面直角座標系へ変換
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)

    x_list = []
    y_list = []
    
    for idx, row in df.iterrows():
        try:
            lat = float(row['Latitude'])
            lon = float(row['Longitude'])
            # 変換実行 (always_xy=True なので経度, 緯度の順で渡す)
            easting, northing = transformer.transform(lon, lat)
            # 日本の平面直角座標系は Xが北向き(Northing)、Yが東向き(Easting)
            x_list.append(round(northing, 3))
            y_list.append(round(easting, 3))
        except (ValueError, TypeError):
            x_list.append("")
            y_list.append("")
            
    # 列を 'Longitude' の右隣に挿入
    idx_lon = df.columns.get_loc('Longitude')
    df.insert(idx_lon + 1, 'X座標', x_list)
    df.insert(idx_lon + 2, 'Y座標', y_list)
    
    return df

# ==========================================
# ファイルアップロード部
# ==========================================
st.markdown("### ⚙️ 座標系の選択")
coord_choice = st.radio(
    "出力したい座標系を選択してください",
    ("選択しない", "平面直角座標系Ⅷ（８）系", "平面直角座標系Ⅹ（１０）系")
)

st.markdown("### 📂 データ読み込み")
uploaded_file = st.file_uploader("GPXファイルをアップロードしてください", type=["gpx"])

if uploaded_file is not None:
    with st.spinner('データを変換中...'):
        file_content = uploaded_file.read()
        df = process_gpx(file_content)
        
        # 座標変換関数を呼び出し
        df = add_xy_coordinates(df, coord_choice)
    
    st.success("✅ 変換が完了しました！")
    
    df = df.fillna("")
    st.dataframe(df, use_container_width=True)
    
    st.markdown("### 💾 ダウンロード")
    st.write("用途に合わせて形式を選び、ダウンロードしてください。（Excelで見る場合は「Excel (.xlsx)」が最も文字化けしにくくオススメです）")
    
    # ボタンを横並びにする
    col1, col2, col3 = st.columns(3)
    
    with col1:
        # --- 1. Excel (.xlsx) ダウンロード ---
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Geology_Data')
        
        st.download_button(
            label="📊 Excel (.xlsx) をダウンロード",
            data=buffer.getvalue(),
            file_name="geology_data.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        
    with col2:
        # --- 2. CSV (.csv) ダウンロード ---
        # WindowsのExcel対策でBOM付きUTF-8 (utf-8-sig) を使用
        csv_data = df.to_csv(index=False, encoding='utf-8-sig')
        st.download_button(
            label="📝 CSV (.csv) をダウンロード",
            data=csv_data,
            file_name="geology_data.csv",
            mime="text/csv"
        )
        
    with col3:
        # --- 3. Text (.txt) ダウンロード ---
        # タブ区切り(TSV)として出力
        txt_data = df.to_csv(index=False, sep='\t', encoding='utf-8')
        st.download_button(
            label="📄 Text (.txt) をダウンロード",
            data=txt_data,
            file_name="geology_data.txt",
            mime="text/plain"
        )