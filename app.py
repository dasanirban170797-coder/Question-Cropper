from collections import defaultdict
import os
import zipfile
import fitz  # PyMuPDF
from PIL import Image
import numpy as np
import streamlit as st


def get_q_starts(page):
  d = page.get_text("dict")
  starts = []
  for block in d["blocks"]:
    if "lines" not in block:
      continue
    for line in block["lines"]:
      txt = "".join([s["text"] for s in line["spans"]]).strip()
      if not txt:
        continue
      x, y = line["bbox"][0], line["bbox"][1]
      if not (x < 80 or (300 < x < 350)):
        continue
      if txt and txt[0].isdigit():
        num = ""
        for ch in txt:
          if ch.isdigit():
            num += ch
          else:
            break
        if not num or len(txt) <= len(num):
          continue
        if txt[len(num)] != ".":
          continue
        if len(txt) > len(num) + 1 and txt[len(num) + 1].isdigit():
          continue
        starts.append({"q": int(num), "y": y, "x": x, "page": page.number})
  uniq, seen = [], set()
  for s in sorted(
      starts, key=lambda s: (0 if s["x"] < 150 else 1, s["y"])
  ):
    if s["q"] not in seen:
      uniq.append(s)
      seen.add(s["q"])
  return uniq


def trim_y_only(img, pad=12):
  gray = img.convert("L")
  arr = np.array(gray)
  mask = arr < 240
  if not mask.any():
    return img
  rows = np.where(mask.any(axis=1))[0]
  y0, y1 = max(0, rows[0] - pad), min(gray.height, rows[-1] + pad)
  return img.crop((0, y0, gray.width, y1))


def crop_pdf_universal(pdf_path, out_dir):
  doc = fitz.open(pdf_path)
  all_starts = []
  for pno in range(len(doc)):
    all_starts.extend(get_q_starts(doc.load_page(pno)))
  all_starts.sort(key=lambda s: (s["page"], 0 if s["x"] < 150 else 1, s["y"]))

  page_dict = defaultdict(list)
  for s in all_starts:
    page_dict[s["page"]].append(s)

  os.makedirs(out_dir, exist_ok=True)
  for s in all_starts:
    pno = s["page"]
    page = doc.load_page(pno)
    col = 0 if s["x"] < 150 else 1

    left_cnt = len([t for t in page_dict[pno] if t["x"] < 150])
    right_cnt = len([t for t in page_dict[pno] if t["x"] >= 150])
    is_double = left_cnt >= 2 and right_cnt >= 2

    same_col = [
        t
        for t in page_dict[pno]
        if (0 if t["x"] < 150 else 1) == col and t["y"] > s["y"]
    ]
    same_col.sort(key=lambda t: t["y"])

    y0 = s["y"] - 4
    y1 = same_col[0]["y"] - 6 if same_col else page.rect.height - 10

    if is_double:
      clip = (
          fitz.Rect(5, y0, page.rect.width / 2 - 5, y1)
          if col == 0
          else fitz.Rect(page.rect.width / 2 + 5, y0, page.rect.width
