"""Build icc-reference.docx, the Word template the paper is rendered into.

Encodes the layout rules of the 2027 ICC Author Instruction Manual: Times New
Roman 11 pt, single spacing, one-inch margins, no paragraph indent, bold
headings, line numbers restarting on each page, and no page numbers.

    python make_reference_docx.py        # needs python-docx and quarto on PATH
"""
import subprocess
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor

HERE = Path(__file__).parent
OUT = HERE / "icc-reference.docx"
FONT = "Times New Roman"


def set_font(style, size=11, bold=None, italic=None, caps=None):
    f = style.font
    f.name, f.size, f.color.rgb = FONT, Pt(size), RGBColor(0, 0, 0)
    if bold is not None:
        f.bold = bold
    if italic is not None:
        f.italic = italic
    if caps is not None:
        f.all_caps = caps
    rpr = style.element.get_or_add_rPr()
    fonts = rpr.find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        rpr.append(fonts)
    for attr in ("ascii", "hAnsi", "eastAsia", "cs"):
        fonts.set(qn(f"w:{attr}"), FONT)
    for attr in ("asciiTheme", "hAnsiTheme", "eastAsiaTheme", "cstheme"):
        fonts.attrib.pop(qn(f"w:{attr}"), None)


def set_para(style, before=0, after=11, align=None):
    pf = style.paragraph_format
    pf.space_before, pf.space_after = Pt(before), Pt(after)
    pf.line_spacing, pf.first_line_indent, pf.left_indent = 1.0, Pt(0), Pt(0)
    if align is not None:
        pf.alignment = align


raw = HERE / "_pandoc_default.docx"
with open(raw, "wb") as fh:
    fh.write(subprocess.run(
        ["quarto", "pandoc", "--print-default-data-file", "reference.docx"],
        check=True, capture_output=True).stdout)
doc = Document(raw)
raw.unlink()

styles = doc.styles
for st in styles:
    if st.type != 1:  # paragraph styles only
        continue
    name = st.name
    if name.startswith("Heading"):
        level = int(name.split()[-1]) if name.split()[-1].isdigit() else 9
        # Main headings bold; subheadings bold; third level bold italic.
        set_font(st, bold=True, italic=(level >= 3))
        set_para(st, before=0, after=11)
        st.paragraph_format.keep_with_next = True
    elif name == "Title":
        set_font(st, bold=True, caps=True)
        set_para(st, after=11, align=WD_ALIGN_PARAGRAPH.LEFT)
    elif name in ("Author", "Date", "Abstract", "Compact", "Body Text",
                  "First Paragraph", "Block Text", "Footnote Text",
                  "Table Caption", "Image Caption", "Figure", "Captioned Figure",
                  "Bibliography", "Normal"):
        set_font(st, bold=False, italic=False)
        set_para(st, after=11)
        if name == "Block Text":  # quotations of 40+ words are the only indent
            st.paragraph_format.left_indent = Inches(0.5)
            st.paragraph_format.right_indent = Inches(0.5)
        if name in ("Compact",):
            set_para(st, after=0)
    elif name == "Title Subtitle" or name == "Subtitle":
        set_font(st, bold=False)
        set_para(st, after=11)

for name in ("Body Text Char", "Verbatim Char", "Hyperlink"):
    try:
        st = styles[name]
    except KeyError:
        continue
    st.font.name = FONT if name != "Verbatim Char" else "Courier New"
    st.font.size = Pt(11)
    if name == "Hyperlink":
        st.font.color.rgb = RGBColor(0, 0, 0)

sec = doc.sections[0]
sec.page_width, sec.page_height = Inches(8.5), Inches(11)
sec.left_margin = sec.right_margin = sec.top_margin = sec.bottom_margin = Inches(1)
# Line numbers (manual: "Add line numbers ... as in this document"), numbered
# continuously down the manuscript; no page numbers anywhere.
for old in sec._sectPr.findall(qn("w:lnNumType")):
    sec._sectPr.remove(old)
ln = OxmlElement("w:lnNumType")
ln.set(qn("w:countBy"), "1")
ln.set(qn("w:restart"), "continuous")
ln.set(qn("w:distance"), "360")
# lnNumType must precede pgNumType/cols in the schema order.
anchor = sec._sectPr.find(qn("w:pgNumType"))
if anchor is None:
    anchor = sec._sectPr.find(qn("w:cols"))
if anchor is not None:
    anchor.addprevious(ln)
else:
    sec._sectPr.append(ln)

doc.save(OUT)
print("wrote", OUT)
