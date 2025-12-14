// 数据可视化工具 - 前端脚本
let currentFileId = null;
let currentVariables = [];

// DOM 元素
const fileInput = document.getElementById('fileInput');
const fileInfo = document.getElementById('fileInfo');
const controlsSection = document.getElementById('controlsSection');
const variablesContainer = document.getElementById('variablesContainer');
const chartType = document.getElementById('chartType');
const generateChartBtn = document.getElementById('generateChart');
const status = document.getElementById('status');
const chartArea = document.getElementById('chartArea');

// 服务器连接检测
const SERVER_PORTS = [8000, 5000];
let serverUrl = '';

async function detectServer() {
    for (let port of SERVER_PORTS) {
        try {
            const response = await fetch(`http://127.0.0.1:${port}/health`, {
                method: 'GET',
                timeout: 3000
            });
            if (response.ok) {
                serverUrl = `http://127.0.0.1:${port}`;
                updateStatus(`✅ 连接到服务器: ${serverUrl}`);
                return true;
            }
        } catch (error) {
            continue;
        }
    }
    
    updateStatus('❌ 无法连接到服务器，请确保后端服务正在运行');
    return false;
}

// 状态更新
function updateStatus(message, isError = false) {
    const statusElement = document.getElementById('status');
    if (statusElement) {
        statusElement.textContent = message;
        statusElement.className = isError ? 'status error' : 'status';
    }
}

// 文件上传处理
fileInput.addEventListener('change', async function(e) {
    const file = e.target.files[0];
    if (!file) return;

    updateStatus('📤 正在上传文件...');
    
    const formData = new FormData();
    formData.append('file', file);

    try {
        const response = await fetch(`${serverUrl}/upload`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || '上传失败');
        }

        const data = await response.json();
        
        // 存储文件信息
        currentFileId = data.file_id;
        currentVariables = data.variables;
        
        // 显示文件信息
        fileInfo.innerHTML = `
            <div class="file-details">
                <strong>📄 文件名:</strong> ${data.file_info.filename}<br>
                <strong>📊 数据量:</strong> ${data.file_info.rows} 行 × ${data.file_info.columns} 列<br>
                <strong>🏷️ 变量数:</strong> ${data.variables.length} 个
            </div>
        `;

        // 显示变量选择控件
        displayVariables(data.variables);
        controlsSection.style.display = 'block';
        
        updateStatus('✅ 文件上传成功！请选择变量生成图表');
        
    } catch (error) {
        updateStatus(`❌ 文件上传失败: ${error.message}`, true);
        console.error('Upload error:', error);
    }
});

// 显示变量选择界面
function displayVariables(variables) {
    variablesContainer.innerHTML = '';
    
    variables.forEach(variable => {
        const label = document.createElement('label');
        label.className = 'variable-checkbox';
        
        const checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.value = variable;
        checkbox.id = `var_${variable}`;
        
        const span = document.createElement('span');
        span.textContent = variable;
        
        label.appendChild(checkbox);
        label.appendChild(span);
        variablesContainer.appendChild(label);
    });
    
    // 添加全选/全不选按钮
    const selectAllContainer = document.createElement('div');
    selectAllContainer.className = 'select-all-container';
    
    const selectAllBtn = document.createElement('button');
    selectAllBtn.textContent = '全选';
    selectAllBtn.className = 'btn-secondary';
    selectAllBtn.onclick = () => toggleAllVariables(true);
    
    const deselectAllBtn = document.createElement('button');
    deselectAllBtn.textContent = '全不选';
    deselectAllBtn.className = 'btn-secondary';
    deselectAllBtn.onclick = () => toggleAllVariables(false);
    
    selectAllContainer.appendChild(selectAllBtn);
    selectAllContainer.appendChild(deselectAllBtn);
    variablesContainer.appendChild(selectAllContainer);
}

// 切换所有变量选择状态
function toggleAllVariables(select) {
    const checkboxes = variablesContainer.querySelectorAll('input[type="checkbox"]');
    checkboxes.forEach(checkbox => checkbox.checked = select);
}

// 获取选中的变量
function getSelectedVariables() {
    const checkboxes = variablesContainer.querySelectorAll('input[type="checkbox"]:checked');
    return Array.from(checkboxes).map(cb => cb.value);
}

// 生成图表
generateChartBtn.addEventListener('click', async function() {
    if (!currentFileId) {
        updateStatus('❌ 请先上传数据文件', true);
        return;
    }

    const selectedVars = getSelectedVariables();
    if (selectedVars.length === 0) {
        updateStatus('❌ 请至少选择一个变量', true);
        return;
    }

    const selectedChartType = chartType.value;
    
    // 验证图表类型要求
    if (selectedChartType === 'pie' && selectedVars.length !== 1) {
        updateStatus('❌ 饼图只能选择一个变量', true);
        return;
    }
    
    if (selectedChartType === 'scatter' && selectedVars.length < 2) {
        updateStatus('❌ 散点图至少需要选择两个变量', true);
        return;
    }

    updateStatus('📊 正在生成图表...');
    
    try {
        const response = await fetch(`${serverUrl}/plot`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                file_id: currentFileId,
                selected_vars: selectedVars,
                plot_type: selectedChartType
            })
        });

        if (!response.ok) {
            const errorData = await response.json();
            throw new Error(errorData.error || '图表生成失败');
        }

        // 显示图表
        const imageUrl = URL.createObjectURL(await response.blob());
        chartArea.innerHTML = `
            <div class="chart-display">
                <img src="${imageUrl}" alt="Generated Chart" class="chart-image">
                <div class="chart-info">
                    <p><strong>图表类型:</strong> ${getChartTypeName(selectedChartType)}</p>
                    <p><strong>使用变量:</strong> ${selectedVars.join(', ')}</p>
                </div>
            </div>
        `;
        
        updateStatus('✅ 图表生成成功！');
        
    } catch (error) {
        updateStatus(`❌ 图表生成失败: ${error.message}`, true);
        console.error('Plot error:', error);
    }
});

// 获取图表类型中文名
function getChartTypeName(type) {
    const typeNames = {
        'bar': '柱状图',
        'line': '折线图',
        'pie': '饼图',
        'hist': '直方图',
        'scatter': '散点图'
    };
    return typeNames[type] || type;
}

// 图表类型变化时自动更新选择提示
chartType.addEventListener('change', function() {
    const selectedType = this.value;
    
    // 根据图表类型调整变量选择建议
    if (selectedType === 'pie') {
        updateStatus('💡 提示：饼图建议选择一个分类变量');
    } else if (selectedType === 'scatter') {
        updateStatus('💡 提示：散点图需要选择两个数值变量');
    } else {
        updateStatus('📊 请选择变量生成图表');
    }
});

// 页面加载时检测服务器
document.addEventListener('DOMContentLoaded', async function() {
    updateStatus('🔍 正在连接服务器...');
    
    const connected = await detectServer();
    if (!connected) {
        // 显示手动连接选项
        setTimeout(() => {
            updateStatus('❌ 无法自动连接服务器，请确保后端服务正在运行', true);
        }, 3000);
    }
});

// 错误处理
window.addEventListener('error', function(e) {
    console.error('JavaScript error:', e.error);
    updateStatus('❌ 页面出现错误，请刷新重试', true);
});

// 网络错误处理
window.addEventListener('unhandledrejection', function(e) {
    console.error('Unhandled promise rejection:', e.reason);
    updateStatus('❌ 网络请求失败，请检查服务器连接', true);
});