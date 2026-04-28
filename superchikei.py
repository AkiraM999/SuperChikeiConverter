import streamlit as st
import pandas as pd
import xml.etree.ElementTree as ET
import io

# ページ設定
st.set_page_config(page_title="GPX to QGIS Database", layout="wide")
st.title("📍 調査用GPXデータ 変換ツール(β版)")

# アイコンと岩相の対応辞書
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
    
    # 文字化け防止のため、文字列としてデコードしてからパース
    content_str = file_content.decode('utf-8', errors='replace')
    tree = ET.parse(io.StringIO(content_str))
    root = tree.getroot()
    
    data_list = []
    
    for wpt in root.findall('default:wpt', ns):
        lat = wpt.get('lat')
        lon = wpt.get('lon')
        
        ele = wpt.find('default:ele', ns).text if wpt.find('default:ele', ns) is not None else ""
        time = wpt.find('default:time', ns).text if wpt.find('default:time', ns) is not None else ""
        name = wpt.find('default:name', ns).text if wpt.find('default:name', ns) is not None else ""
        cmt = wpt.find('default:cmt', ns).text if wpt.find('default:cmt', ns) is not None else ""
        
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

        # ---------------------------------------------
        # 写真情報（linkタグ）の抽出
        # ---------------------------------------------
        photo_dict = {}
        links = wpt.findall('default:link', ns)
        for i, link in enumerate(links, start=1):
            # href属性からファイル名を取得
            href = link.get('href')
            if href:
                photo_dict[f'Photo_{i}'] = href

        # 判定ロジック
        lithology = LITHOLOGY_MAPPING.get(icon_num, "") 
        road_closed_flag = True if icon_num == ROAD_CLOSED_ICON else False
        
        text_lower = f"{yomi} {cmt}".lower()
        text_raw = f"{yomi} {cmt}"
        
        sample_flag = True if "sample" in text_lower else False
        magne_flag = True if "帯磁率" in text_raw else False

        # 1行分のデータを辞書にまとめる
        row_data = {
            'Point_Name': name,
            'Latitude': lat,
            'Longitude': lon,
            'Elevation': ele,
            'Time': time,
            'Lithology': lithology,
            'Sample_Flag': sample_flag,
            'Magne_Flag': magne_flag,
            'Road_Closed': road_closed_flag,
            'Comment': cmt,
            'Yomi': yomi,
            'Icon_Num': icon_num
        }
        
        # 写真データを合体させる (Photo_1, Photo_2... が末尾に追加される)
        row_data.update(photo_dict)
        
        data_list.append(row_data)
        
    # DataFrameに変換（列が存在しない行は自動的に空欄になる）
    return pd.DataFrame(data_list)


# ==========================================
# Streamlit UI
# ==========================================
uploaded_file = st.file_uploader("GPXファイルをアップロードしてください", type=["gpx"])

if uploaded_file is not None:
    with st.spinner('データを変換中...'):
        file_content = uploaded_file.read()
        df = process_gpx(file_content)
    
    st.success("✅ 変換が完了しました！")
    
    # 欠損値（NaN）を空文字に置き換えて見やすくする
    df = df.fillna("")
    
    st.dataframe(df, use_container_width=True)
    
    st.markdown("### 💾 ダウンロード設定")
    # 文字コードを選択させる
    encoding_choice = st.radio(
        "CSVの文字コードを選んでください（文字化けする場合は変更してください）",
        ("UTF-8 (BOM付き) - 多くの環境で推奨", "Shift-JIS - WindowsのExcelで直接開く場合", "UTF-8 - QGIS等の標準")
    )
    
    # 選択された文字コードに応じてエンコーディングを設定
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