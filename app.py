# -*- encoding=utf8 -*-
__author__ = "小小的太阳"
import os
import socket
import re
import subprocess
import time
from datetime import datetime
from flask import Flask, jsonify, request, send_file, render_template, send_from_directory
from apscheduler.schedulers.background import BackgroundScheduler

app = Flask(__name__)
# 创建一个后台调度器
scheduler = BackgroundScheduler()

# 获取本机ip 但保存127.0.0.1，防止切换ip或者挂vpn后，地址乱跳
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
    adb_command = f"adb -s {device} shell pm list package"
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
        # 临时将上传的文件重命名为 test.py 防止乱七八糟的名字
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
    
# 打开html
@app.route('/get_html_url', methods=['GET'])
def get_html_url():
    html_url = request.args.get('html_url')
    device = request.args.get('device')
    print(device)
    print(html_url)
    command = f"adb -s {device} shell am start -a android.intent.action.VIEW -d {html_url}"
    return_code = os.system(command)
    if return_code == 0:
        return jsonify({'message': f'成功打开URL：{html_url}'})

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
    # 截图的adb命令
    os.system(f"adb -s {device} exec-out screencap -p > {screenshot_path}")
    return screenshot_path

# 开始录制屏幕
@app.route('/start_recording', methods=['POST'])
def start_recording():
    device = request.args.get('device')
    if not device:
        return jsonify({'message': '请指定设备'}), 400
    
    # 生成带时间戳的文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"screen_record_{device}_{timestamp}.mp4"
    
    # 启动录制进程
    try:
        # 使用adb screenrecord命令，限制为180秒，分辨率720p，1280x720
        command = f"adb -s {device} shell screenrecord --verbose --time-limit 180 --size 1280x720 /sdcard/{filename}"
        # 在后台运行录制命令
        subprocess.Popen(command, shell=True)
        
        # 返回文件名用于下载
        return jsonify({
            'message': '开始录制屏幕',
            'filename': filename,
            'status': 'recording'
        })
    except Exception as e:
        return jsonify({'message': f'开始录制失败: {str(e)}'}), 500

# 停止录制并下载
@app.route('/stop_and_download_recording', methods=['POST'])
def stop_and_download_recording():
    device = request.args.get('device')
    filename = request.args.get('filename')

    if not device or not filename:
        return jsonify({'message': '参数错误'}), 400

    video_path = f"./uploads/{filename}"
    try:
        # 停止录制并拉取视频
        os.system(f"adb -s {device} shell pkill -l SIGINT screenrecord")
        time.sleep(1)  # 等待视频生成
        # 将视频从设备拉取到本地
        os.system(f"adb -s {device} pull /sdcard/{filename} ./uploads/{filename}")
        # 删除设备上的临时文件
        os.system(f"adb -s {device} shell rm /sdcard/{filename}")

        if not os.path.exists(video_path):
            return jsonify({'message': '录制文件未找到'}), 404

        # 创建响应并发送文件
        response = send_file(video_path, as_attachment=True)
        return response
    except Exception as e:
        return jsonify({'message': f'操作失败: {e}'}), 500
    # 无论怎样都删除临时文件夹的视频
    finally:
        try:
            if os.path.exists(video_path):
                print("删除文件")
                os.remove(video_path)
                app.logger.info(f"成功删除文件: {video_path}")
        except Exception as e:
            print("删除文件失败")
            app.logger.error(f"删除文件 {video_path} 时出错: {e}")


# 获取录制状态，辅助功能，暂时不需要调用
@app.route('/get_recording_status')
def get_recording_status():
    device = request.args.get('device')
    if not device:
        return jsonify({'message': '请指定设备'}), 400
    
    # 检查设备上是否有screenrecord进程
    try:
        result = subprocess.run(
            f"adb -s {device} shell ps | grep screenrecord",
            shell=True,
            capture_output=True,
            text=True
        )
        
        if result.stdout.strip():
            return jsonify({'status': 'recording'})
        else:
            return jsonify({'status': 'stopped'})
    except Exception as e:
        return jsonify({'message': f'获取状态失败: {str(e)}'}), 500
    

# 开始monkey测试
@app.route('/start_monkey_test', methods=['POST'])
def start_monkey_test():
    device = request.args.get('device')
    
    if not device:
        return jsonify({
            'status': 'error',
            'message': '设备参数不能为空'
        }), 400
    
    # 获取当前屏幕上包名
    package_name = get_current_package(device)
    if not package_name:
        return jsonify({
            'status': 'error',
            'message': '无法获取当前应用包名'
        }), 400
    
    # 设置Monkey测试参数
    event_count = 10000  # 执行事件的数量
    throttle = 300   # 事件间隔300ms
    pct_touch = 80  # 点击事件比例
    pct_motion = 20 # 滑动事件比例

    # 确保其他事件类型比例为 0
    pct_trackball = 0
    pct_nav = 0
    pct_syskeys = 0
    pct_appswitch = 0
    pct_flip = 0
    pct_anyevent = 0
    
    try:
        
        # 启动Monkey测试
        command = (
            f"adb -s {device} shell monkey -p {package_name} "
            f"--throttle {throttle} "
            f"--pct-touch {pct_touch} "
            f"--pct-motion {pct_motion} "
            f"--pct-trackball {pct_trackball} "
            f"--pct-nav {pct_nav} "
            f"--pct-syskeys {pct_syskeys} "
            f"--pct-appswitch {pct_appswitch} "
            f"--pct-flip {pct_flip} "
            f"--pct-anyevent {pct_anyevent} "
            f"{event_count}"
    )
        subprocess.Popen(command, shell=True)
        
        # 保存启动参数用于展示信息
        return jsonify({
            'status': 'success',
            'message': 'Monkey测试已启动',
            'package_name': package_name,
            'event_count': event_count,
            'throttle': throttle,
            'pct_touch':pct_touch,
            'pct_motion':pct_motion,
        })
        
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': f'启动Monkey测试失败: {str(e)}'
        }), 500


# 停止测试，暂时不知道如何停止


# adb logcat功能
@app.route('/export_logcat', methods=['GET'])
def export_logcat():
    device = request.args.get('device')
    if not device:
        return jsonify({'status': 'error', 'message': '需要设备参数'}), 400

    try:
        # 生成带时间戳的日志文件，并保存为txt格式
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = f"./uploads/logcat_{device}_{timestamp}.txt"
        
        # 导出日志命令
        os.system(f"adb -s {device} logcat -d > {log_file}")
        
        if not os.path.exists(log_file):
            return jsonify({'status': 'error', 'message': '日志生成失败'}), 500
            
        return jsonify({
            'status': 'success',
            'log_file': log_file,
            'message': '日志已生成'
        })
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'导出失败: {str(e)}'}), 500

# 下载并删除临时文件
@app.route('/download_logcat', methods=['GET'])
def download_logcat():
    log_file = request.args.get('log_file')
    if not log_file or not os.path.exists(log_file):
        return jsonify({'status': 'error', 'message': '文件不存在'}), 404
    
    try:
        response = send_file(log_file, as_attachment=True)
        return response
    except Exception as e:
        return jsonify({'status': 'error', 'message': f'下载失败: {str(e)}'}), 500
    # 无论怎样都删除临时log文件
    finally:
        try:
            if os.path.exists(log_file):
                os.remove(log_file)
                app.logger.info(f"已删除临时日志: {log_file}")
        except Exception as e:
            app.logger.error(f"删除文件失败: {str(e)}")

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

# 获取帧率数据
@app.route('/get_frame_rate')
def get_frame_rate():
    package_name = request.args.get('package')
    if not package_name:
        return jsonify({'error': 'Package parameter is required'}), 400
    
    frame_rate = get_frame_rate_for_package(package_name)
    return jsonify({'frame_rate': frame_rate})

def get_frame_rate_for_package(package_name):
    try:
        # 执行adb命令获取帧率信息
        adb_command = f"adb shell dumpsys gfxinfo {package_name}"
        result = subprocess.run(adb_command, shell=True, capture_output=True, text=True)

        # 打印输出，以便调试
        print(result.stdout)

        # 从输出中提取总帧数和掉帧数
        output = result.stdout.strip()
        frames_rendered_match = re.search(r'Total frames rendered: (\d+)', output)
        janky_frames_match = re.search(r'Janky frames: (\d+)', output)

        if frames_rendered_match and janky_frames_match:
            total_frames = int(frames_rendered_match.group(1))
            janky_frames = int(janky_frames_match.group(1))

            # 计算帧率
            if total_frames > 0:
                frame_rate = (total_frames - janky_frames) / total_frames * 60
            else:
                frame_rate = 0.0

            return round(frame_rate, 2)
        else:
            print("Failed to parse frame rate data.")
            return 0.0

    except Exception as e:
        print(f"Error while fetching frame rate: {e}")
        return 0.0
if __name__ == '__main__':
    app.run(host=get_host_ip(), port=1111, debug=True, threaded=True)