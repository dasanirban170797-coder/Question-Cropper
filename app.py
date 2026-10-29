import fitz
from PIL import Image
import os, zipfile
import numpy as np
from collections import defaultdict
import streamlit as st
import tempfile

def get_q_starts(page):
    d = page.get_text("dict")
    starts=[]
    for block in d['blocks']:
        if 'lines' not in block: continue
        for line in block['lines']:
            txt = "".join([s['text'] for s in line['spans']]).strip()
            if not txt: continue
            x, y = line['bbox'][0], line['bbox'][1]
            if not (x < 80 or (300 < x < 350)): continue
            if txt and txt[0].isdigit():
                num=""
                for ch in txt:
                    if ch.isdigit(): num+=ch
                    else: break
                if not num or len(txt)<=len(num): continue
                if txt[len(num)] != '.': continue
                if len(txt) > len(num)+1 and txt[len(num)+1].isdigit(): continue
                starts.append({'q': int(num), 'y': y, 'x': x, 'page': page.number})
    uniq, seen=[], set()
    for s in sorted(starts, key=lambda s: (0 if s['x']<150 else 1, s['y'])):
        if s['q'] not in seen:
            uniq.append(s); seen.add(s['q'])
    return uniq

def trim_y_only(img, pad=12):
    gray = img.convert("L")
    arr = np.array(gray)
    mask = arr < 240
    if not mask.any(): return img
    rows = np.where(mask.any(axis=1))[0]
    y0, y1 = max(0, rows[0]-pad), min(gray.height, rows[-1]+pad)
    return img.crop((0, y0, gray.width, y1))

def crop_pdf_universal(pdf_path, out_dir):
    doc = fitz.open(pdf_path)
    all_starts=[]
    for pno in range(len(doc)): all_starts.extend(get_q_starts(doc.load_page(pno)))
    all_starts.sort(key=lambda s: (s['page'], 0 if s['x']<150 else 1, s['y']))
    page_dict = defaultdict(list)
    for s in all_starts: page_dict[s['page']].append(s)
    os.makedirs(out_dir, exist_ok=True)

    for s in all_starts:
        pno = s['page']
        page = doc.load_page(pno)
        col = 0 if s['x']<150 else 1
        left_cnt = len([t for t in page_dict[pno] if t['x']<150])
        right_cnt = len([t for t in page_dict[pno] if t['x']>=150])
        is_double = left_cnt>=2 and right_cnt>=2
        same_col = [t for t in page_dict[pno] if (0 if t['x']<150 else 1)==col and t['y']>s['y']]
        same_col.sort(key=lambda t: t['y'])
        y0 = s['y']-4
        y1 = same_col[0]['y']-6 if same_col else page.rect.height-10
        
        if is_double:
            clip = fitz.Rect(5, y0, page.rect.width/2-5, y1) if col==0 else fitz.Rect(page.rect.width/2+5, y0, page.rect.width-10, y1)
        else:
            clip = fitz.Rect(5, y0, page.rect.width-10, y1)
        
        txt = page.get_text(clip=clip)
        has_complete = "(4)" in txt or "(D)" in txt
        pix = page.get_pixmap(dpi=350, clip=clip)
        img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

        if not has_complete and col==0 and not same_col and is_double:
            right_list = sorted([t for t in page_dict[pno] if t['x']>=150], key=lambda t: t['y'])
            if right_list:
                r_clip = fitz.Rect(page.rect.width/2+5, 0, page.rect.width-10, right_list[0]['y']-6)
                r_txt = page.get_text(clip=r_clip)
                if r_txt.strip() and "(1)" in r_txt:
                    r_pix = page.get_pixmap(dpi=350, clip=r_clip)
                    r_img = Image.frombytes("RGB", [r_pix.width, r_pix.height], r_pix.samples)
                    img1 = trim_y_only(img, 12)
                    img2 = trim_y_only(r_img, 12)
                    GAP = 8  
                    merged = Image.new("RGB", (max(img1.width, img2.width), img1.height+GAP+img2.height), "white")
                    merged.paste(img1, (0,0))
                    merged.paste(img2, (0, img1.height+GAP))
                    img = merged
                else:
                    img = trim_y_only(img, 12)
            else:
                img = trim_y_only(img, 12)
        else:
            img = trim_y_only(img, 12)
        
        img.save(f"{out_dir}/Q_{s['q']}.jpg")

st.title("PDF Question Cropper")

uploaded_file = st.file_uploader("Upload your PDF file", type=["pdf"])

if uploaded_file is not None:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_file:
        tmp_file.write(uploaded_file.read())
        pdf_path = tmp_file.name

    out_dir = "FINAL"
    if st.button("Crop Questions"):
        with st.spinner("Cropping questions..."):
            crop_pdf_universal(pdf_path, out_dir)
            
            zip_path = "FINAL.zip"
            with zipfile.ZipFile(zip_path, 'w') as z:
                for f in sorted(os.listdir(out_dir), key=lambda x: int(x.split('_')[1].split('.')[0])):
                    z.write(os.path.join(out_dir, f), f)
            
            st.success(f"DONE {len(os.listdir(out_dir))} Qs")
            
            with open(zip_path, "rb") as fp:
                st.download_button(
                    label="Download ZIP",
                    data=fp,
                    file_name="FINAL.zip",
                    mime="application/zip"
                )
