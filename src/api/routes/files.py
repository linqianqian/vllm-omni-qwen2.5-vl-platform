"""
文件上传和解析路由
支持 PDF、Word、Excel、文本文件
"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
import io
import os

router = APIRouter()


def parse_pdf(file_bytes: bytes) -> str:
    """解析 PDF 文件"""
    try:
        import PyPDF2
        pdf_file = io.BytesIO(file_bytes)
        pdf_reader = PyPDF2.PdfReader(pdf_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return text.strip()
    except ImportError:
        raise HTTPException(status_code=500, detail="请安装 PyPDF2: pip install PyPDF2")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"PDF解析失败: {str(e)}")


def parse_word(file_bytes: bytes) -> str:
    """解析 Word 文件"""
    try:
        from docx import Document
        doc_file = io.BytesIO(file_bytes)
        doc = Document(doc_file)
        text = ""
        for para in doc.paragraphs:
            text += para.text + "\n"
        return text.strip()
    except ImportError:
        raise HTTPException(status_code=500, detail="请安装 python-docx: pip install python-docx")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Word解析失败: {str(e)}")


def parse_excel(file_bytes: bytes) -> str:
    """解析 Excel 文件"""
    try:
        import pandas as pd
        excel_file = io.BytesIO(file_bytes)
        xls = pd.ExcelFile(excel_file)
        text_parts = []
        for sheet_name in xls.sheet_names:
            df = pd.read_excel(xls, sheet_name=sheet_name)
            text_parts.append(f"=== {sheet_name} ===\n")
            text_parts.append(df.to_string(index=False))
            text_parts.append("\n")
        return "\n".join(text_parts).strip()
    except ImportError:
        raise HTTPException(status_code=500, detail="请安装 pandas: pip install pandas openpyxl")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Excel解析失败: {str(e)}")


def parse_text(file_bytes: bytes) -> str:
    """解析文本文件"""
    encodings = ['utf-8', 'gbk', 'gb2312', 'latin-1']
    for encoding in encodings:
        try:
            return file_bytes.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise HTTPException(status_code=400, detail="无法识别文件编码")


@router.post("/parse")
async def parse_file(file: UploadFile = File(...)):
    """
    上传并解析文件，返回文本内容
    支持: .pdf, .docx, .xlsx, .xls, .txt, .md, .py, .js, .html 等
    """
    # 最大内容长度限制（约 8000 字符，避免超出 API 限制）
    MAX_CONTENT_LENGTH = 8000
    
    # 检查文件大小 (最大 10MB)
    max_size = 10 * 1024 * 1024
    file_bytes = await file.read()
    if len(file_bytes) > max_size:
        raise HTTPException(status_code=400, detail="文件大小超过10MB限制")
    
    # 空文件检查
    if len(file_bytes) == 0:
        raise HTTPException(status_code=400, detail="文件为空")
    
    # 获取文件扩展名
    filename = file.filename or ""
    ext = os.path.splitext(filename.lower())[1]
    
    # 根据文件类型解析
    if ext == '.pdf':
        content = parse_pdf(file_bytes)
    elif ext in ['.docx', '.doc']:
        content = parse_word(file_bytes)
    elif ext in ['.xlsx', '.xls']:
        content = parse_excel(file_bytes)
    elif ext in ['.txt', '.md', '.py', '.js', '.html', '.css', '.json', '.xml', '.csv', '.log']:
        content = parse_text(file_bytes)
    else:
        # 尝试作为文本解析
        try:
            content = parse_text(file_bytes)
        except HTTPException:
            raise HTTPException(
                status_code=400, 
                detail=f"不支持的文件格式: {ext}，支持的格式: pdf, docx, xlsx, xls, txt, md, py, js, html, css, json, csv"
            )
    
    # 截断过长的内容
    original_length = len(content)
    is_truncated = False
    if len(content) > MAX_CONTENT_LENGTH:
        content = content[:MAX_CONTENT_LENGTH] + "\n\n[内容已截断，原文过长]"
        is_truncated = True
    
    return JSONResponse({
        "status": "success",
        "filename": filename,
        "type": ext.lstrip('.') if ext else "unknown",
        "content": content,
        "length": len(content),
        "original_length": original_length,
        "is_truncated": is_truncated
    })


@router.get("/supported")
async def get_supported_types():
    """获取支持的文件类型列表"""
    return {
        "supported_types": [
            {"ext": ".pdf", "name": "PDF文档", "icon": "📄"},
            {"ext": ".docx", "name": "Word文档", "icon": "📝"},
            {"ext": ".xlsx", "name": "Excel表格", "icon": "📊"},
            {"ext": ".xls", "name": "Excel表格(旧版)", "icon": "📊"},
            {"ext": ".txt", "name": "文本文件", "icon": "📃"},
            {"ext": ".md", "name": "Markdown", "icon": "📝"},
            {"ext": ".py", "name": "Python代码", "icon": "🐍"},
            {"ext": ".js", "name": "JavaScript", "icon": "📜"},
            {"ext": ".html", "name": "HTML文件", "icon": "🌐"},
            {"ext": ".csv", "name": "CSV表格", "icon": "📊"},
        ],
        "max_size_mb": 10
    }
