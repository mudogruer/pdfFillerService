# ------------------------------------------------------------------------------

# atk pdf fill function

# ------------------------------------------------------------------------------
import base64
import json
import io
from typing import Any, Dict
from flask import Flask, request, Response, jsonify

app = Flask(__name__)


def pxJson(obj: Any, key: str, default: Any = None) -> Any:
	"""Safely get a value from a dict by key; returns default if missing or obj not dict."""
	try:
		if isinstance(obj, dict):
			return obj.get(key, default)
		return default
	except Exception:
		return default


def pxConvertRequest() -> Dict[str, Any]:
	"""Convert current Flask request to expected object format for atkFillPdfFromData.
	Supports multipart/form-data with 'pdf' file and 'fields'/'images' (JSON) or application/json body.
	"""
	result: Dict[str, Any] = {}
	ct = (request.content_type or '').lower()
	try:
		if 'multipart/form-data' in ct:
			pdf_file = request.files.get('pdf')
			if pdf_file:
				pdf_bytes = pdf_file.read()
				result['pdf'] = base64.b64encode(pdf_bytes).decode('ascii')
			fields_raw = request.form.get('fields')
			fields: Dict[str, Any] = {}
			if fields_raw:
				try:
					fields = json.loads(fields_raw)
				except Exception:
					fields = {}
			result['data'] = fields
			images_raw = request.form.get('images')
			if images_raw:
				try:
					images = json.loads(images_raw)
					if isinstance(images, dict):
						result['images'] = images
				except Exception:
					pass
			readonly = request.form.get('readonly')
			flatten = request.form.get('flatten')
			form = {}
			if readonly is not None:
				form['readonly'] = str(readonly).lower() in ['1', 'true', 'on', 'yes']
			if flatten is not None:
				form['flatten'] = str(flatten).lower() in ['1', 'true', 'on', 'yes']
			if form:
				result['form'] = form
		elif 'application/json' in ct:
			payload = request.get_json(silent=True) or {}
			if isinstance(payload, dict):
				result = payload
		else:
			# Try to read raw body as JSON
			payload = request.get_json(silent=True) or {}
			if isinstance(payload, dict):
				result = payload
	except Exception:
		pass
	return result
def atkFillPdfFromData(obj):
    # Mustafa Dogruer : 21.08.2025 
    # fill pdf from data
    # obj = {
    #     "pdf": "<base64|bytes>",
    #     "data": {
    #         "field1": "value1",  # text/numeric values are written directly to matching form fields
    #         "check1": true,        # checkboxes accept true/false, 1/0, yes/no, on/off, x
    #
    #         # image-by-field (legacy/compatible):
    #         "Image9_af_image": {"source": "<url|www.|data-url|base64|bytes>", "preserveAspect": true, "maxBytes": 10485760},
    #         "Image10_af_image": {"source": "<...>"}
    #     },
    #     "form": {
    #         "readonly": true, # if true, the form fields will be readonly
    #         "flatten": true # if true, the form fields will be flattened
    #     },
    #     "images": {                # preferred image map (same structure as per-field), overrides data.* images
    #         "Image9_af_image": {"source": "<url|www.|data-url|base64|bytes>", "keepProportion": true},
    #         "Image10_af_image": {"source": "<...>"}
    #     },
    #     "return": "base64|bytes",   # For direct output, backward-compatible.
    #
    #     # OR, for advanced file saving options:
    #     "return": {
    #       "mode": "file",            # Accepted modes for saving: "file", "save", "path".
    #       "filename": "output.pdf",    # Optional. Defaults to "atkfile.pdf".
    #       "directory": "/var/tmp",   # Optional. Defaults to a "downloads" subdir in the current working directory.
    #       "overwrite": false,        # Optional. If false, avoids overwriting by creating a new unique name (e.g., "output(2).pdf").
    #       "mkdirs": true             # Optional. If true, creates the destination directory if it does not exist.
    #     }
    # }
    #
    # How it works (short):
    # - Uses PyMuPDF (fitz) to load the PDF and iterate page widgets (form fields)
    # - Fills text/numeric fields by matching field names in data
    # - For images: finds a field with the same name (usually button/widget), gets its rect, and inserts the image there
    # - Template/content is preserved; we do not rebuild or merge pages, only update widget values and draw image into its own rect
    #
    # Image handling:
    # - source supports: full http(s) URL, bare "www.*" (auto-normalized to https://), data URLs (data:image/*;base64,...),
    #   raw base64 strings, or raw bytes
    # - keepProportion/preserveAspect (bool): controls aspect ratio (default True if not provided)
    # - maxBytes (int): server-side guard for downloaded images (default 10MB)
    # - Timeout for URL fetches: 10 seconds (best-effort)
    #
    # Returns:
    # - { report: "success", pdf: <base64|bytes>, meta: { bytes: <len> } }
    # - { report: "success", message: "File saved", path: "/path/to/file.pdf" }
    # - On error: { report: "error", code: "ATKPDF-xx", message: "..." }
    #   Codes: ATKPDF-01 (missing input), ATKPDF-02 (missing fitz), ATKPDF-03 (decode fail),
    #          ATKPDF-04 (processing fail), ATKPDF-05 (encode fail), ATKPDF-06 (file save fail)
    #
    # Notes:
    # - Images can be provided either under data.* (legacy) or under images.* (preferred). If both exist, images.* wins.
	# safe base64 decoder with padding and urlsafe fallback
    
	def _decode_b64_bytes(s):
		if not isinstance(s, str): return None
		val = s.strip()
		if val.startswith('data:image'):
			parts = val.split(',', 1)
			if len(parts) == 2: val = parts[1]
		val = ''.join(val.split())
		pad = len(val) % 4
		if pad: val += '=' * (4 - pad)
		try: return base64.b64decode(val)
		except Exception:
			try: return base64.urlsafe_b64decode(val)
			except Exception: return None

	# --- Input Processing ---
	obj = obj or {}
	custom = obj
	try: # service call fallback
		if not pxJson(custom, 'pdf'):
			reqx = pxConvertRequest()
			if isinstance(reqx, dict) and pxJson(reqx, 'pdf'): custom = reqx
	except Exception: pass
	
	pdf_input = pxJson(custom, 'pdf') or pxJson(custom, 'file')
	field_values = pxJson(custom, 'data') or {}
	image_items = pxJson(custom, 'images') or {}
	# form options
	form_conf = pxJson(custom, 'form') or {}
	form_readonly = bool(pxJson(form_conf, 'readonly')) if isinstance(form_conf, dict) else False
	form_flatten = bool(pxJson(form_conf, 'flatten')) if isinstance(form_conf, dict) else False
	
	return_config = pxJson(custom, 'return') or 'base64'
	ret_mode = 'base64'
	file_save_options = None

	if isinstance(return_config, str):
		ret_mode = return_config.lower()
	elif isinstance(return_config, dict):
		ret_mode = (return_config.get('mode') or 'base64').lower()
		if ret_mode in ['file', 'pdf', 'path', 'save']:
			file_save_options = return_config

	# Backward compatibility: find images in `data` if not in `images`
	if isinstance(field_values, dict):
		for k, v in field_values.items():
			if k not in image_items and isinstance(v, dict) and 'source' in v:
				image_items[k] = v

	if not pdf_input:
		return {"report": "error", "message": "PDF 'pdf' or 'file' key required.", "code": "ATKPDF-01"}

	# --- Library Import ---
	try:
		import fitz # PyMuPDF
	except ImportError:
		return {"report": "error", "message": "PyMuPDF (fitz) is required. Please install it.", "code": "ATKPDF-02"}
	
	# --- PDF Decoding ---
	pdf_bytes = None
	try:
		if isinstance(pdf_input, str):
			pdf_bytes = _decode_b64_bytes(pdf_input)
		elif isinstance(pdf_input, (bytes, bytearray)):
			pdf_bytes = bytes(pdf_input)
		if not pdf_bytes: raise ValueError("PDF input could not be decoded to bytes.")
	except Exception as e:
		return {"report": "error", "message": f"PDF decoding failed: {e}", "code": "ATKPDF-03"}

	# --- Core PDF Processing with Fitz ---
	doc = None
	try:
		doc = fitz.open(stream=pdf_bytes, filetype="pdf")
		
		# Process all pages for widgets (form fields)
		for page in doc:
			# collect widgets to optionally flatten after processing
			_page_widgets = list(page.widgets()) or []
			for widget in _page_widgets:
				field_name = widget.field_name

				# 1. Form Field Filling
				if field_name in field_values:
					try:
						value = field_values[field_name]
						if widget.field_type == fitz.PDF_WIDGET_TYPE_CHECKBOX:
							# Handle boolean-like values for checkboxes
							if str(value).lower() in ['true', '1', 'yes', 'on', 'x']:
								widget.field_value = True
							else:
								widget.field_value = False
						elif widget.field_type != fitz.PDF_WIDGET_TYPE_BUTTON:
							widget.field_value = str(value)
						widget.update()
					except Exception as e:
						return {'report':'error','message':'PDF processing failed','code':'ATKPDF-04'}

				# 1.1 Readonly handling (if requested)
				if form_readonly:
					try:
						# common patterns across fitz versions
						if hasattr(widget, 'set_readonly') and callable(getattr(widget, 'set_readonly')):
							widget.set_readonly(True)
						else:
							ff = getattr(widget, 'field_flags', None)
							if isinstance(ff, int):
								try:
									widget.field_flags = ff | 1
								except Exception:
									pass
						widget.update()
					except Exception:
						pass

				# 2. Image Placement on existing fields
				if field_name in image_items:
					try:
						cfg = image_items[field_name]
						src = pxJson(cfg, 'source') or pxJson(cfg, 'data') or pxJson(cfg, 'url')
						if not src: 
							continue

						img_bytes = None
						if isinstance(src, (bytes, bytearray)):
							img_bytes = bytes(src)
						elif isinstance(src, str):
							src_clean = src.strip()
							# normalize bare www.* to https://
							if src_clean.startswith('www.'):
								src_clean = 'https://' + src_clean
							if src_clean.startswith('http'):
								try:
									import requests
									max_bytes = int(pxJson(cfg, 'maxBytes') or 10485760)
									resp = requests.get(src_clean, timeout=10)
									if resp.ok and len(resp.content) <= max_bytes:
										img_bytes = resp.content
								except Exception:
									img_bytes = None
							else: # Assume base64 or data-url
								img_bytes = _decode_b64_bytes(src_clean)
								if not img_bytes and len(src_clean) > 10:
									try:
										mb = len(src_clean) % 4
										img_bytes = base64.b64decode(src_clean + ('=' * (4 - mb) if mb else ''))
									except Exception:
										img_bytes = None
						
						if img_bytes:
							# Use the widget's rectangle for perfect placement
							rect = widget.rect
							preserve = pxJson(cfg, 'preserveAspect')
							if preserve is None:
								preserve = pxJson(cfg, 'keepProportion')
							keep_prop = True if preserve is None else bool(preserve)
							try:
								page.insert_image(rect, stream=img_bytes, keep_proportion=keep_prop, overlay=True)
							except Exception:
								pass
					except Exception:
						pass

			# 3. Process images that don't match any existing fields (place at coordinates or anchor)
			for field_name, cfg in image_items.items():
				# Skip if already processed above
				if any(w.field_name == field_name for w in _page_widgets):
					continue
				try:
					src = pxJson(cfg, 'source') or pxJson(cfg, 'data') or pxJson(cfg, 'url')
					if not src: 
						continue
					img_bytes = None
					if isinstance(src, (bytes, bytearray)):
						img_bytes = bytes(src)
					elif isinstance(src, str):
						src_clean = src.strip()
						if src_clean.startswith('www.'):
							src_clean = 'https://' + src_clean
						if src_clean.startswith('http'):
							try:
								import requests
								max_bytes = int(pxJson(cfg, 'maxBytes') or 10485760)
								resp = requests.get(src_clean, timeout=10)
								if resp.ok and len(resp.content) <= max_bytes:
									img_bytes = resp.content
							except Exception:
								img_bytes = None
						else:
							img_bytes = _decode_b64_bytes(src_clean)
							if not img_bytes and len(src_clean) > 10:
								try:
									mb = len(src_clean) % 4
									img_bytes = base64.b64decode(src_clean + ('=' * (4 - mb) if mb else ''))
								except Exception:
									img_bytes = None
					if img_bytes:
						anchor_name = pxJson(cfg, 'anchor')
						anchor_rect = None
						if anchor_name:
							for w in _page_widgets:
								if getattr(w, 'field_name', None) == anchor_name:
									anchor_rect = getattr(w, 'rect', None)
									break
						fit_to_anchor = bool(pxJson(cfg, 'fitToAnchor'))
						if anchor_rect and fit_to_anchor:
							rect = anchor_rect
						else:
							x = pxJson(cfg, 'x') or (float(anchor_rect.x0) if anchor_rect else 50)
							y = pxJson(cfg, 'y') or (float(anchor_rect.y0) if anchor_rect else 50)
							width = pxJson(cfg, 'width') or (float(anchor_rect.width) if anchor_rect else 100)
							height = pxJson(cfg, 'height') or (float(anchor_rect.height) if anchor_rect else 100)
							rect = fitz.Rect(x, y, x + width, y + height)
						preserve = pxJson(cfg, 'preserveAspect')
						if preserve is None:
							preserve = pxJson(cfg, 'keepProportion')
						keep_prop = True if preserve is None else bool(preserve)
						try:
							page.insert_image(rect, stream=img_bytes, keep_proportion=keep_prop, overlay=True)
						except Exception:
							pass
				except Exception:
					pass

			# 4. Flatten widgets on this page if requested (remove interactivity)
			if form_flatten and _page_widgets:
				for _w in _page_widgets:
					try:
						_w.delete()
					except Exception:
						pass

		# Save the modified PDF to bytes
		out_bytes = doc.tobytes()

	except Exception as e:
		return {"report": "error", "message": f"PDF processing failed: {e}", "code": "ATKPDF-04"}
	finally:
		if doc: doc.close()

	# --- Return Result ---
	meta_base = {"bytes": len(out_bytes)}
	from pathlib import Path
	if file_save_options:
		try:
			directory_str = file_save_options.get('directory') or str(Path.cwd() / 'downloads')
			directory = Path(directory_str).expanduser()
			filename = file_save_options.get('filename') or 'atkfile.pdf'
			overwrite = file_save_options.get('overwrite', False)
			mkdirs = file_save_options.get('mkdirs', True)

			if mkdirs:
				directory.mkdir(parents=True, exist_ok=True)
			# resolve to absolute path after potential creation
			try:
				directory = directory.resolve()
			except Exception:
				pass

			final_path = directory / filename
			if not overwrite:
				base, ext = final_path.stem, final_path.suffix
				counter = 1
				while final_path.exists():
					counter += 1
					final_path = directory / f"{base}({counter}){ext}"
			
			final_path.write_bytes(out_bytes)
			try:
				abs_path = str(final_path.resolve())
			except Exception:
				abs_path = str(final_path)
			return {"report": "success", "message": "File saved successfully", "path": abs_path}
		except Exception as e:
			return {"report": "error", "message": f"Failed to save file: {e}", "code": "ATKPDF-06"}

	elif ret_mode == 'bytes':
		return Response(out_bytes, mimetype='application/pdf')
	else: # base64
		try:
			# Ensure we are encoding bytes
			pdf_bytes = out_bytes
			if isinstance(pdf_bytes, str):
				pdf_bytes = out_bytes.encode('latin-1')
			
			b64 = base64.b64encode(pdf_bytes).decode('ascii')
			return {"report": "success", "message": "PDF processed successfully", "code": "200", "pdf": b64, "meta": meta_base}
		except Exception as e:
			return {"report": "error", "message": f"Base64 encoding failed: {e}", "code": "ATKPDF-05"}


# ----------------------------- Flask Endpoints -----------------------------

@app.route('/')
def index():
	return Response(
		'''<!DOCTYPE html>
		<html lang="tr">
		<head>
			<meta charset="UTF-8" />
			<meta name="viewport" content="width=device-width, initial-scale=1" />
			<title>PDF Form Filler</title>
			<style>
				:root { --bg:#0f172a; --panel:#0f1a2e; --muted:#93a4b8; --accent:#22c55e; --accent2:#3b82f6; --input:#121c32; --input-border:#3a4a66; --input-border-focus:#60a5fa; }
				body{margin:0;background:var(--bg);color:#e5e7eb;font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,sans-serif}
				.container{max-width:1120px;margin:24px auto;padding:0 16px}
				.card{background:var(--panel);border:1px solid #1f2a44;border-radius:14px;overflow:hidden;box-shadow:0 10px 30px rgba(0,0,0,.35)}
				.header{padding:16px 20px;border-bottom:1px solid #1f2a44;display:flex;align-items:center;justify-content:space-between}
				.title{font-size:18px;font-weight:700}
				.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;padding:16px}
				.vstack{display:flex;flex-direction:column;gap:18px;padding:16px}
				.section{border:1px dashed #2b3a54;border-radius:12px;padding:14px}
				label{display:block;font-size:12px;color:#b5c3d6;margin-bottom:6px}
				input[type="text"], textarea{box-sizing:border-box;width:100%;background:var(--input);border:1px solid var(--input-border);border-radius:10px;color:#e5eef8;padding:12px 12px;font-size:14px}
				textarea{min-height:96px;max-height:240px;resize:vertical;overflow:auto}
				input[type="file"]{width:100%;background:var(--input);border:1px solid var(--input-border);border-radius:10px;color:#e5eef8;padding:10px}
				input::placeholder, textarea::placeholder{color:#a6b4c6}
				input:focus, textarea:focus{outline:none;border-color:var(--input-border-focus);box-shadow:0 0 0 2px rgba(96,165,250,.25)}
				.btn{cursor:pointer;user-select:none;border:0;border-radius:10px;padding:10px 14px;font-weight:700;letter-spacing:.2px}
				.btn-primary{background:var(--accent2);color:white}
				.btn-outline{background:transparent;border:1px solid #405170;color:#d2deea}
				.btn:hover{filter:brightness(1.05)}
				.row{display:grid;grid-template-columns:220px 1fr 120px;gap:12px;align-items:start}
				.row button{align-self:start}
				.rows{display:flex;flex-direction:column;gap:12px;margin-top:10px}
				.kv{display:flex;gap:8px;align-items:flex-start}
				kbd{background:#111827;border:1px solid #374151;border-bottom-width:2px;padding:2px 6px;border-radius:6px;color:#9ca3af}
				.preview{height:78vh;border:0;width:100%;background:#0b1220;border-top:1px solid #1f2937}
				.badge{font-size:12px;background:#111827;border:1px solid #334155;border-radius:999px;padding:4px 10px;color:#9ca3af}
			</style>
		</head>
		<body>
			<div class="container">
				<div class="card">
					<div class="header">
						<div class="title">PDF Form Filler</div>
						<div class="badge">Upload → Map Fields → Show PDF</div>
					</div>
					<div class="vstack">
						<div class="section">
							<label>Upload PDF</label>
							<input id="pdfFile" type="file" accept="application/pdf" />
							<div style="display:flex;gap:8px;margin-top:10px">
								<label style="display:flex;align-items:center;gap:6px"><input id="optReadonly" type="checkbox" checked /> Readonly</label>
								<label style="display:flex;align-items:center;gap:6px"><input id="optFlatten" type="checkbox" checked /> Flatten</label>
							</div>
						</div>
						<div class="section">
							<div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
								<label>Fields (ID / Value)</label>
								<button class="btn btn-outline" id="btnAdd">+ Add Field</button>
							</div>
							<div class="rows" id="rows"></div>
						</div>
						<div class="section">
							<div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
								<label>Images (Field ID / Source)</label>
								<button class="btn btn-outline" id="btnAddImg">+ Add Image</button>
							</div>
							<div class="rows" id="imgRows"></div>
							<div style="color:#9ca3af;font-size:12px;margin-top:8px">Source can be URL, data URL or base64. You can also choose a local image file.</div>
						</div>
					</div>
					<div style="display:flex;gap:10px;justify-content:flex-end;padding:12px 16px;border-top:1px solid #1f2937">
						<button class="btn btn-outline" id="btnReset">Reset</button>
						<button class="btn btn-outline" id="btnShow">Show PDF</button>
						<a id="btnDownload" class="btn btn-outline" download="filled.pdf" href="#" style="display:none">Download</a>
					</div>
					<iframe id="preview" class="preview"></iframe>
				</div>
			</div>
			<script>
				let fieldList = [];
				const rowsEl = document.getElementById('rows');
				const imgRowsEl = document.getElementById('imgRows');
				const btnAdd = document.getElementById('btnAdd');
				const btnAddImg = document.getElementById('btnAddImg');
				const btnShow = document.getElementById('btnShow');
				const btnReset = document.getElementById('btnReset');
				const pdfInput = document.getElementById('pdfFile');
				const optReadonly = document.getElementById('optReadonly');
				const optFlatten = document.getElementById('optFlatten');
				const preview = document.getElementById('preview');
				const btnDownload = document.getElementById('btnDownload');

				const dl = document.createElement('datalist');
				dl.id = 'fieldList';
				document.body.appendChild(dl);

				function setIdSuggestions(inputEl){ inputEl.setAttribute('list','fieldList'); }
				function renderFieldList(){
					dl.innerHTML = '';
					for(const name of fieldList){ const opt = document.createElement('option'); opt.value = name; dl.appendChild(opt); }
				}

				function createRowWithId(fieldId, value='') {
					const wrapper = document.createElement('div');
					wrapper.className = 'row';
					const id = document.createElement('input');
					id.type = 'text'; id.placeholder = 'Field ID (PDF form field name)'; id.value = fieldId || '';
					const val = document.createElement('textarea');
					val.placeholder = 'Value (long text scrollable)'; val.value = value || '';
					const del = document.createElement('button');
					del.className = 'btn btn-outline'; del.textContent = 'Remove';
					del.onclick = () => wrapper.remove();
					wrapper.appendChild(id); wrapper.appendChild(val); wrapper.appendChild(del);
					rowsEl.appendChild(wrapper);
					setIdSuggestions(id);
				}

				function isImageId(name){
					const n = String(name||'');
					return /(af_image|image|img|logo|qr|barcode|photo|picture)/i.test(n);
				}

				function createImgRowWith(fieldId){
					createImgRow();
					const row = imgRowsEl.lastElementChild;
					if(!row) return;
					const inputs = row.querySelectorAll('input,textarea');
					// indices: 0 id, 1 textarea, 2 file, 3 anchor, 4 fit, 5 keep, 6 max, 7 x, 8 y, 9 w, 10 h
					if(inputs[0]) inputs[0].value = fieldId || '';
					if(inputs[3]) inputs[3].value = fieldId || '';
					if(inputs[4]) inputs[4].checked = true;
				}

				async function fetchFields(){
					const file = pdfInput.files && pdfInput.files[0];
					if(!file) return;
					try{
						const fd = new FormData(); fd.append('pdf', file);
						const res = await fetch('/api/fields', { method:'POST', body: fd });
						const data = await res.json();
						fieldList = Array.isArray(data?.fields) ? data.fields.map(f=>f.name).filter(Boolean) : [];
						renderFieldList();
						// Auto-populate panels
						rowsEl.innerHTML = '';
						imgRowsEl.innerHTML = '';
						const fields = Array.isArray(data?.fields) ? data.fields : [];
						for(const f of fields){
							const name = f?.name;
							if(!name) continue;
							if(isImageId(name)) createImgRowWith(name); else createRowWithId(name, '');
						}
					}catch(e){ /* ignore */ }
				}

				function createRow() {
					const wrapper = document.createElement('div');
					wrapper.className = 'row';
					const id = document.createElement('input');
					id.type = 'text'; id.placeholder = 'Field ID (PDF form field name)';
					const val = document.createElement('textarea');
					val.placeholder = 'Value (long text scrollable)';
					const del = document.createElement('button');
					del.className = 'btn btn-outline'; del.textContent = 'Remove';
					del.onclick = () => wrapper.remove();
					wrapper.appendChild(id); wrapper.appendChild(val); wrapper.appendChild(del);
					rowsEl.appendChild(wrapper);
					setIdSuggestions(id);
				}

				btnAdd.addEventListener('click', () => createRow());
				btnReset.addEventListener('click', () => {
					rowsEl.innerHTML = '';
					imgRowsEl.innerHTML = '';
					preview.src = '';
					btnDownload.style.display = 'none';
					pdfInput.value = '';
				});

				function collectFields() {
					const data = {};
					for (const row of rowsEl.children) {
						const [idEl, valEl] = row.querySelectorAll('input,textarea');
						const key = (idEl.value || '').trim();
						if (!key) continue;
						data[key] = valEl.value;
					}
					return data;
				}

				function createImgRow() {
					const wrapper = document.createElement('div');
					wrapper.className = 'row';
					const id = document.createElement('input');
					id.type = 'text'; id.placeholder = 'Field ID (image field name)';
					const src = document.createElement('textarea');
					src.placeholder = 'Source (URL, data URL or base64). If a file is selected, this is ignored.';
					const del = document.createElement('button');
					del.className = 'btn btn-outline'; del.textContent = 'Remove';
					del.onclick = () => wrapper.remove();

					const file = document.createElement('input');
					file.type = 'file'; file.accept = 'image/*';
					file.style = 'grid-column: 1 / span 2';

					const options = document.createElement('div');
					options.style = 'grid-column: 1 / span 3; display:flex; flex-wrap:wrap; gap:12px; align-items:center; color:#b5c3d6; font-size:12px;';
					const anchorWrap = document.createElement('label');
					const anchor = document.createElement('input'); anchor.type = 'text'; anchor.placeholder = 'Anchor field (optional)'; anchor.style = 'width:220px;'; anchor.setAttribute('list','fieldList');
					anchorWrap.appendChild(document.createTextNode(' Anchor: ')); anchorWrap.appendChild(anchor);
					const fitLab = document.createElement('label');
					const fitCb = document.createElement('input'); fitCb.type = 'checkbox'; fitCb.checked = true; fitLab.appendChild(fitCb); fitLab.appendChild(document.createTextNode(' Fit to anchor'));
					const keep = document.createElement('label');
					const keepCb = document.createElement('input'); keepCb.type = 'checkbox'; keepCb.checked = true; keep.appendChild(keepCb); keep.appendChild(document.createTextNode(' Keep aspect ratio'));
					const max = document.createElement('label');
					const maxIn = document.createElement('input'); maxIn.type = 'text'; maxIn.placeholder = 'Max bytes (default 10485760)'; maxIn.style = 'width:180px;';
					max.appendChild(document.createTextNode(' ')); max.appendChild(maxIn);
					
					const coords = document.createElement('div');
					coords.style = 'display:flex; gap:8px; align-items:center; margin-top:8px;';
					const xLabel = document.createElement('label');
					const xIn = document.createElement('input'); xIn.type = 'text'; xIn.placeholder = 'X'; xIn.style = 'width:60px;';
					xLabel.appendChild(document.createTextNode('X:')); xLabel.appendChild(xIn);
					const yLabel = document.createElement('label');
					const yIn = document.createElement('input'); yIn.type = 'text'; yIn.placeholder = 'Y'; yIn.style = 'width:60px;';
					yLabel.appendChild(document.createTextNode('Y:')); yLabel.appendChild(yIn);
					const wLabel = document.createElement('label');
					const wIn = document.createElement('input'); wIn.type = 'text'; wIn.placeholder = 'Width'; wIn.style = 'width:70px;';
					wLabel.appendChild(document.createTextNode('W:')); wLabel.appendChild(wIn);
					const hLabel = document.createElement('label');
					const hIn = document.createElement('input'); hIn.type = 'text'; hIn.placeholder = 'Height'; hIn.style = 'width:70px;';
					hLabel.appendChild(document.createTextNode('H:')); hLabel.appendChild(hIn);
					coords.appendChild(xLabel); coords.appendChild(yLabel); coords.appendChild(wLabel); coords.appendChild(hLabel);
					
					options.appendChild(anchorWrap); options.appendChild(fitLab); options.appendChild(keep); options.appendChild(max);
					options.appendChild(coords);

					wrapper.appendChild(id);
					wrapper.appendChild(src);
					wrapper.appendChild(del);
					wrapper.appendChild(file);
					wrapper.appendChild(options);

					imgRowsEl.appendChild(wrapper);
					setIdSuggestions(id);
				}

				btnAddImg && btnAddImg.addEventListener('click', () => createImgRow());

				async function showPdf() {
					const file = pdfInput.files && pdfInput.files[0];
					if (!file) { alert('Please select a PDF.'); return; }
					const form = new FormData();
					form.append('pdf', file);
					form.append('fields', JSON.stringify(collectFields()));
					if (imgRowsEl) {
						const items = {};
						const toB64 = f => new Promise((resolve,reject)=>{ const r = new FileReader(); r.onload=()=>resolve(String(r.result)); r.onerror=reject; r.readAsDataURL(f); });
						const promises = [];
						for (const row of imgRowsEl.children) {
							const inputs = row.querySelectorAll('input,textarea');
							const idEl = inputs[0];
							const srcEl = inputs[1];
							const fileEl = inputs[2];
							const keepCb = inputs[3];
							const maxIn = inputs[4];
							const xIn = inputs[5];
							const yIn = inputs[6];
							const wIn = inputs[7];
							const hIn = inputs[8];
							const anchorIn = inputs[9];
							const fitAnchorCb = inputs[10];
							const field = (idEl && idEl.value || '').trim();
							if (!field) continue;
							items[field] = { source: (srcEl && srcEl.value || '').trim(), preserveAspect: keepCb ? !!keepCb.checked : true };
							if (maxIn && maxIn.value) items[field].maxBytes = Number(maxIn.value) || maxIn.value;
							if (xIn && xIn.value) items[field].x = Number(xIn.value) || 50;
							if (yIn && yIn.value) items[field].y = Number(yIn.value) || 50;
							if (wIn && wIn.value) items[field].width = Number(wIn.value) || 100;
							if (hIn && hIn.value) items[field].height = Number(hIn.value) || 100;
							if (anchorIn && anchorIn.value) items[field].anchor = anchorIn.value.trim();
							if (fitAnchorCb) items[field].fitToAnchor = !!fitAnchorCb.checked;
							if (fileEl && fileEl.files && fileEl.files[0]) {
								promises.push(toB64(fileEl.files[0]).then(b64 => { items[field].source = String(b64); }));
							}
						}
						await Promise.all(promises);
						form.append('images', JSON.stringify(items));
					}
					form.append('readonly', optReadonly.checked ? 'true' : 'false');
					form.append('flatten', optFlatten.checked ? 'true' : 'false');
					try {
						const res = await fetch('/api/fill', { method: 'POST', body: form });
						if (!res.ok) { const t = await res.text(); throw new Error(t || 'Request failed'); }
						const blob = await res.blob();
						const url = URL.createObjectURL(blob);
						preview.src = url;
						btnDownload.href = url;
						btnDownload.style.display = 'inline-block';
					} catch (err) {
						alert('Error: ' + (err && err.message ? err.message : err));
					}
				}

				pdfInput.addEventListener('change', fetchFields);
				btnShow.addEventListener('click', showPdf);
				createRow();
			</script>
			</body>
			</html>''',
			mimetype='text/html; charset=utf-8'
	)


@app.route('/api/fill', methods=['POST'])
def api_fill():
	try:
		obj = pxConvertRequest()
		if not obj or not pxJson(obj, 'pdf'):
			return jsonify({"report": "error", "message": "Missing PDF upload."}), 400
		# Force bytes return so we can stream PDF
		obj['return'] = 'bytes'
		res = atkFillPdfFromData(obj)
		if isinstance(res, Response):
			return res
		if isinstance(res, dict) and res.get('report') == 'success' and 'pdf' in res:
			# In case of base64 fallback, decode and return bytes
			data = base64.b64decode(res['pdf'])
			return Response(data, mimetype='application/pdf')
		if isinstance(res, dict) and res.get('report') == 'success' and res.get('path'):
			# If saved to disk, read and stream
			p = res.get('path')
			try:
				with open(p, 'rb') as f:
					return Response(f.read(), mimetype='application/pdf')
			except Exception:
				return jsonify({"report": "error", "message": "File saved but could not be read."}), 500
		# Error case
		return jsonify(res), 400
	except Exception as e:
		return jsonify({"report": "error", "message": str(e)}), 500


@app.route('/api/fields', methods=['POST'])
def api_fields():
	try:
		from flask import request
		pdf_file = request.files.get('pdf')
		if not pdf_file:
			return jsonify({"fields": []})
		import fitz
		doc = fitz.open(stream=pdf_file.read(), filetype='pdf')
		fields = []
		for page in doc:
			for w in list(page.widgets() or []):
				try:
					name = getattr(w, 'field_name', None)
					type_code = getattr(w, 'field_type', None)
					rect = getattr(w, 'rect', None)
					fields.append({
						"name": name, 
						"type": int(type_code) if isinstance(type_code, int) else None,
						"rect": str(rect) if rect else None
					})
				except Exception:
					pass
		doc.close()
		# unique by name, keep order
		seen = set()
		unique = []
		for f in fields:
			n = f.get('name')
			if n and n not in seen:
				seen.add(n)
				unique.append(f)
		return jsonify({"fields": unique})
	except Exception:
		return jsonify({"fields": []})


if __name__ == '__main__':
	import os
	port = int(os.environ.get('PORT', '5000'))
	host = os.environ.get('HOST', '0.0.0.0')
	app.run(host=host, port=port)
