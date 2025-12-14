from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import pandas as pd
import matplotlib
matplotlib.use('Agg')  # 设置为非交互式后端
import matplotlib.pyplot as plt
import io
import os
import tempfile
import logging
from werkzeug.utils import secure_filename
from datetime import datetime

# 配置日志 - 减少日志输出提高性能
logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)  # 启用跨域支持
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size
# 性能优化配置
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # 禁用缓存
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False  # 禁用JSON美化
app.config['DEBUG'] = False  # 关闭调试模式

# 存储上传文件的临时目录
UPLOAD_FOLDER = tempfile.mkdtemp()
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 存储上传文件的字典，用于会话管理
uploaded_files = {}

ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def cleanup_old_files():
    current_time = datetime.now()
    files_to_remove = []
    
    for file_id, (filepath, upload_time) in uploaded_files.items():
        if (current_time - upload_time).seconds > 3600:
            try:
                if os.path.exists(filepath):
                    os.remove(filepath)
                files_to_remove.append(file_id)
            except Exception as e:
                logger.error(f"Error removing old file {filepath}: {str(e)}")
    
    for file_id in files_to_remove:
        del uploaded_files[file_id]

# 静态文件路由
@app.route('/styles.css')
def serve_css():
    try:
        with open('styles.css', 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'text/css'}
    except FileNotFoundError:
        logger.error("styles.css file not found")
        return "/* CSS file not found */", 404, {'Content-Type': 'text/css'}

@app.route('/script.js')
def serve_js():
    try:
        with open('script.js', 'r', encoding='utf-8') as f:
            return f.read(), 200, {'Content-Type': 'application/javascript'}
    except FileNotFoundError:
        logger.error("script.js file not found")
        return "// JavaScript file not found", 404, {'Content-Type': 'application/javascript'}

# 主页路由
@app.route('/')
def index():
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            return f.read()
    except FileNotFoundError:
        logger.error("index.html file not found")
        return "<h1>Error: index.html file not found</h1>", 404
    except Exception as e:
        logger.error(f"Error serving index.html: {str(e)}")
        return f"<h1>Error loading page</h1><p>{str(e)}</p>", 500

# 上传路由
@app.route('/upload', methods=['POST', 'OPTIONS'])
def upload_file():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        if 'file' not in request.files:
            logger.warning("No file in request")
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            logger.warning("Empty filename")
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            logger.warning(f"Invalid file type: {file.filename}")
            return jsonify({'error': 'Invalid file type. Supported formats: .csv, .xlsx, .xls'}), 400
        
        # 清理旧文件
        cleanup_old_files()
        
        # 生成唯一文件名
        filename = secure_filename(file.filename)
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        unique_filename = f"{timestamp}_{filename}"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        # 保存文件
        file.save(filepath)
        logger.info(f"File saved: {filepath}")
        
        # 读取文件并获取列名
        try:
            if filename.endswith('.csv'):
                # 尝试多种编码方式
                encodings = ['utf-8', 'gbk', 'gb2312', 'latin1', 'cp1252']
                data = None
                for encoding in encodings:
                    try:
                        data = pd.read_csv(filepath, encoding=encoding)
                        logger.info(f"Successfully read CSV with encoding: {encoding}")
                        break
                    except UnicodeDecodeError:
                        continue
                
                if data is None:
                    raise Exception("Unable to read CSV file with any supported encoding")
            else:
                data = pd.read_excel(filepath)
            
            # 获取列名和基本信息
            variables = list(data.columns)
            file_info = {
                'rows': len(data),
                'columns': len(variables),
                'filename': filename
            }
            
            # 存储文件信息
            file_id = f"file_{timestamp}"
            uploaded_files[file_id] = (filepath, datetime.now())
            
            logger.info(f"File processed successfully: {filename}, {len(data)} rows, {len(variables)} columns")
            
            return jsonify({
                'variables': variables,
                'file_id': file_id,
                'file_info': file_info
            })
            
        except Exception as parse_error:
            logger.error(f"File parsing error: {str(parse_error)}")
            if os.path.exists(filepath):
                os.remove(filepath)
            return jsonify({'error': f'Failed to parse file: {str(parse_error)}. Please ensure the file is in correct format.'}), 400
            
    except Exception as e:
        logger.error(f'File processing error: {str(e)}')
        return jsonify({'error': f'Failed to process file: {str(e)}'}), 500

# 绘图路由
@app.route('/plot', methods=['POST', 'OPTIONS'])
def plot_data():
    if request.method == 'OPTIONS':
        return '', 200
    
    try:
        data = request.json
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        file_id = data.get('file_id')
        selected_vars = data.get('selected_vars')
        plot_type = data.get('plot_type')
        
        if not file_id or not selected_vars or not plot_type:
            return jsonify({'error': 'Missing required parameters'}), 400
        
        # 从存储中获取文件路径
        if file_id not in uploaded_files:
            return jsonify({'error': 'File not found. Please upload the file again.'}), 404
            
        file_path, _ = uploaded_files[file_id]
        
        if not os.path.exists(file_path):
            return jsonify({'error': 'File not found on server. Please upload the file again.'}), 404
        
        # 读取数据
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path, encoding='utf-8')
            else:
                df = pd.read_excel(file_path)
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {str(e)}")
            return jsonify({'error': f'Error reading file: {str(e)}'}), 400
        
        # 验证选择的变量是否存在
        missing_vars = [var for var in selected_vars if var not in df.columns]
        if missing_vars:
            return jsonify({'error': f'Variables not found in file: {", ".join(missing_vars)}'}), 400
        
        # 数据预处理 - 确保数值类型
        try:
            # 对于散点图和线图，需要确保是数值数据
            if plot_type in ['scatter', 'line', 'hist']:
                for var in selected_vars:
                    df[var] = pd.to_numeric(df[var], errors='coerce')
                    # 检查是否有有效数据
                    if df[var].dropna().empty:
                        return jsonify({'error': f'Variable "{var}" contains no valid numeric data'}), 400
            # 对于饼图和柱状图，保持原始类型
        except Exception as preprocess_error:
            return jsonify({'error': f'Data preprocessing failed: {str(preprocess_error)}'}), 400
        
        # 创建图表
        plt.figure(figsize=(10, 6))
        plt.title(f'{plot_type.upper()} Chart', fontsize=16)
        
        try:
            if plot_type == 'pie':
                if len(selected_vars) > 1:
                    return jsonify({'error': 'Pie chart supports only one variable'}), 400
                df[selected_vars[0]].value_counts().plot(kind='pie', autopct='%1.1f%%', figsize=(8, 8))
                
            elif plot_type == 'line':
                df[selected_vars].plot(kind='line', figsize=(12, 6))
                
            elif plot_type == 'bar':
                df[selected_vars].plot(kind='bar', figsize=(10, 6))
                
            elif plot_type == 'hist':
                if len(selected_vars) > 1:
                    return jsonify({'error': 'Histogram supports only one variable'}), 400
                df[selected_vars[0]].plot(kind='hist', bins=20, figsize=(10, 6))
                
            elif plot_type == 'scatter':
                if len(selected_vars) < 2:
                    return jsonify({'error': 'Scatter plot requires at least two variables'}), 400
                df.plot(kind='scatter', x=selected_vars[0], y=selected_vars[1], figsize=(10, 6))
                
            else:
                return jsonify({'error': f'Invalid plot type: {plot_type}'}), 400
            
            # 保存图表到内存
            img = io.BytesIO()
            plt.tight_layout()
            plt.savefig(img, format='png', dpi=150, bbox_inches='tight')
            img.seek(0)
            plt.close()
            
            logger.info(f"Generated {plot_type} plot for variables: {', '.join(selected_vars)}")
            return send_file(img, mimetype='image/png')
            
        except Exception as plot_error:
            plt.close()
            logger.error(f"Plot generation error: {str(plot_error)}")
            return jsonify({'error': f'Error generating plot: {str(plot_error)}'}), 500
            
    except Exception as e:
        logger.error(f"Unexpected error in plot_data: {str(e)}")
        return jsonify({'error': f'An unexpected error occurred: {str(e)}'}), 500

# 健康检查端点
@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'healthy',
        'timestamp': datetime.now().isoformat(),
        'uploaded_files_count': len(uploaded_files)
    })

# 清理临时文件的端点
@app.route('/cleanup', methods=['POST'])
def cleanup():
    try:
        cleanup_old_files()
        return jsonify({'message': 'Cleanup completed'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    cleanup_old_files()
    
    logger.info("Starting Flask server...")
    logger.info(f"Upload folder: {UPLOAD_FOLDER}")
    
    # Get port from environment variable (for Render) or use default
    port = int(os.environ.get('PORT', 8001))
    
    logger.info(f"Server will be available at:")
    logger.info(f"  - Local: http://127.0.0.1:{port}")
    logger.info(f"  - Network: http://0.0.0.0:{port} (other devices can access)")
    
    # 优化的启动参数 - 提高响应速度
    app.run(
        debug=False,  # 关闭调试模式提高性能
        host='0.0.0.0',  # 绑定所有网络接口，允许其他设备访问
        port=port,  # 使用环境变量中的端口或默认8001
        threaded=True,  # 启用多线程
        use_reloader=False  # 禁用重载器
    )