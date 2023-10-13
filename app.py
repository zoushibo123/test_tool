# -*- encoding=utf8 -*-
__author__ = "小小的太阳"
import os
import socket
import re
from flask import Flask, jsonify, request, send_file, render_template, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
# 创建一个后台调度器
scheduler = BackgroundScheduler()

# 获取本机ip 但保存127.0.0.1，就是玩
def get_host_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 82))
        ip = s.getsockname()[0]
    finally:
        s.close()
    # return ip
    return "127.0.0.1"

# 新增一个路由，不使用根路径
@app.route('/')
def index():
    return render_template('index.html')

# 获取设备列表
@app.route('/get_devices')
def get_devices():
    adb_command = "adb devices"
    result = os.popen(adb_command).read()
    devices = [line.split('\t')[0] for line in result.splitlines()[1:] if line.endswith('\tdevice')]
    return jsonify({'devices': devices})

# 获取指定设备上已安装app
def get_installed_apps():
    device = request.args.get('device')
    adb_command = f"adb -s {device} shell pm list packages"
    result = os.popen(adb_command).read()
    apps = [line.split(':')[-1] for line in result.splitlines() if line.startswith('package:')]
    return apps

# 获取app列表
@app.route('/get_app_list')
def get_app_list():
    app_list = get_installed_apps()
    return jsonify({'apps': app_list})

# 模糊搜索包名
@app.route('/search_packages')
def search_packages():
    device = request.args.get('device')
    query = request.args.get('query') 
    if not device or not query:
        return jsonify({'message': '参数错误'})
    # 获取所有已安装的应用列表
    all_apps = get_installed_apps()
    # 使用模糊搜索过滤应用列表
    matches = [app for app in all_apps if query.lower() in app.lower()]
    return jsonify({'matches': matches})

# 重启app
@app.route('/restart_app')
def restart_app():
    device = request.args.get('device')
    activity_package_name = get_current_package(device)
    if activity_package_name:
        os.system(f"adb -s {device} shell am force-stop {activity_package_name}")
        os.system(f"adb -s {device} shell monkey -p {activity_package_name} 1")
        return jsonify({'message': f'已重启应用 {activity_package_name}', 'package_name': activity_package_name})
    else:
        return jsonify({'message': '无法获取当前应用'})

# 清除app数据重启
@app.route('/clear_data')
def clear_data():
    device = request.args.get('device')
    activity_package_name = get_current_package(device)
    if activity_package_name:
        os.system(f"adb -s {device} shell pm clear {activity_package_name}")
        os.system(f"adb -s {device} shell monkey -p {activity_package_name} 1")
        return jsonify({'message': f'数据已清除，应用 {activity_package_name} 已重启', 'package_name': activity_package_name})
    else:
        return jsonify({'message': '无法获取当前应用'})

# 安装apk文件
@app.route('/install_apk', methods=['POST'])
def install_apk():
    device = request.args.get('device')
    uploaded_file = request.files['file']

    if uploaded_file.filename != '':
        # 临时将上传的文件命名为 test.py 防止乱七八糟的名字
        apk_path = f'./uploads/test.apk'
        uploaded_file.save(apk_path)

        # 使用os.system来执行adb命令
        command = f"adb -s {device} install -r {apk_path}"
        return_code = os.system(command)

        os.remove(apk_path)  # 删除临时上传的APK文件

        if return_code == 0:
            return jsonify({'message': f'APK已安装到 {device}'})
        else:
            return jsonify({'message': '安装APK时出错'})
    else:
        return jsonify({'message': '未选择文件'})
    
# 卸载指定设备的指定app
@app.route('/uninstall_apk', methods=['POST'])
def uninstall_apk():
    device = request.args.get('device')
    activity_package_name = get_current_package(device)
    print(activity_package_name)
    command = f"adb -s {device} uninstall {activity_package_name}"
    return_code = os.system(command)
    if return_code == 0:
        return jsonify({'message': f'成功卸载应用：{activity_package_name}'})

# 保存uploads目录
@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory('uploads', filename)

# 保存screenshot目录
@app.route('/screenshot/<filename>')
def get_screenshot(filename):
    return send_from_directory('screenshot', filename)

# 获取包名信息
def get_current_package(device):
    adb_command = f"adb -s {device} shell dumpsys window | grep mCurrentFocus"
    output = os.popen(adb_command).read()
    activity_package_name = output.split()[-1].split('/')[0] if output else None
    return activity_package_name

# 截取手机屏幕
@app.route('/capture_screen')
def capture_screen():
    device = request.args.get('device')
    screenshot_path = f'./screenshot/photo_{device}.png'
    os.system(f"adb -s {device} exec-out screencap -p > {screenshot_path}")
    return screenshot_path

# 运行py文件
@app.route('/run_script', methods=['POST'])
def run_script():
    device = request.args.get('device')
    uploaded_file = request.files['file']

    if not uploaded_file or not uploaded_file.filename.endswith('.py'):
        return jsonify({'message': '请选择一个Python脚本文件'})

    # 临时将上传的文件命名为 test.py 防止乱七八糟的名字
    script_path = f'./uploads/test.py'
    uploaded_file.save(script_path)

    try:
        os.system(f'python3 {script_path}')
        output = '脚本执行成功'
    except Exception as e:
        output = f'脚本执行失败: {e}'
    finally:
        os.remove(script_path)  # 无论是否发生异常，都会执行删除
    return jsonify({'message': output})

# 导出JS日志
@app.route('/export_js_logs_device')
def export_js_logs_device():
    device = request.args.get('device')
    os.system(f"adb -s {device} logcat -d | grep js > logs/js_log.txt")

    if os.path.exists("logs/js_log.txt"):
        return send_file("logs/js_log.txt", as_attachment=True)
    else:
        return jsonify({'message': '导出设备JS日志失败'})

# 获取当前应用的内存使用量
@app.route('/get_memory_usage')
def get_memory_usage():
    device = request.args.get('device')
    package_name = request.args.get('package')  # 从前端获取选中的包名
    if package_name:
        memory_usage = get_current_memory(device, package_name)
        return jsonify({'memory_usage': memory_usage})
    else:
        return jsonify({'message': '无法获取当前应用'})

def get_current_memory(device, package_name):
    adb_command = f"adb -s {device} shell dumpsys meminfo {package_name}"
    output = os.popen(adb_command).readlines()
    for line in output:
        if 'TOTAL' in line:
            memory_usage = int(line.split()[1]) / 1024  # 转换为MB
            return int(memory_usage)
    return 0

# 获取CPU使用率
@app.route('/get_cpu_usage')
def get_cpu_usage():
    device = request.args.get('device')
    package_name = request.args.get('package')  # 从前端获取选中的包名
    if package_name:
        cpu_usage = get_cpu_usage_for_app(device, package_name)
        return jsonify({'cpu_usage': cpu_usage})
    else:
        return jsonify({'message': '无法获取当前应用的 CPU 使用率'})
    
def get_cpu_usage_for_app(device, package_name):
    adb_command = f"adb -s {device} shell cat /proc/cpuinfo | grep processor | wc -l"
    cpu_count = int(os.popen(adb_command).read().strip())

    adb_command = f"adb -s {device} shell top -n 1 -d 1 -b | grep {package_name}"
    output = os.popen(adb_command).readlines()
    if output:
        cpu_usage = float(output[0].split()[8])  # 获取第一个进程的 CPU 使用率
        cpu_usage /= cpu_count  # 计算平均 CPU 使用率
        return cpu_usage
    return 0

# 获取指定设备的帧率
@app.route('/get_frame_rate')
def get_frame_rate():
    device = request.args.get('device')
    print("-------------")
    frame_rate = get_frame_rate_for_device(device)
    return jsonify({'frame_rate': frame_rate})

def get_frame_rate_for_device(device):
    adb_command = f"adb -s {device} shell dumpsys gfxinfo | grep 'Total frames rendered'"
    output = os.popen(adb_command).read()
    frame_count_str = re.search(r'\d+', output)
    if frame_count_str is not None:
        frame_count = int(frame_count_str.group())
    else:
        frame_count = 0
    
    adb_command = f"adb -s {device} shell dumpsys gfxinfo | grep 'Janky frames'"
    output = os.popen(adb_command).read()
    janky_frame_count_str = re.search(r'\d+', output)
    if janky_frame_count_str is not None:
        janky_frame_count = int(janky_frame_count_str.group())
    else:
        janky_frame_count = 0

    frame_rate = (frame_count - janky_frame_count) / frame_count * 60  # 计算帧率
    return round(frame_rate, 2)

if __name__ == '__main__':
    app.run(host=get_host_ip(), port=1111, debug=True, threaded=True)