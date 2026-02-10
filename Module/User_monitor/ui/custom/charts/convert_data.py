import numpy as np


def convert_data_to_cage_format(original_data):
    # 获取列名和中文标题的映射
    columns = original_data['columns']
    columns_title = original_data['columns_title']
    column_mapping = dict(zip(columns, columns_title))

    # 使用字典按时间分组数据
    time_grouped_data = {}

    # 处理每一行数据
    for row in original_data['rows']:
        # 获取时间字符串，从time字段中提取时分秒
        # if row.get('time'):
        #     # 假设time格式是 '2026-01-07 18:00:28.572'
        #     time_str = row['time'].split(' ')[1].split('.')[0]  # 提取 '18:00:28' 部分
        # else:
        #     time_str = None
        if row.get('time') is None:
            time_str = None
        else:
            # 假设time格式是 '2026-01-07 18:00:28.572'
            time_str = row['time'].split('.')[0]  # 提取 '2026-01-07 18:00:28' 部分

        # 如果该时间还未在字典中，则初始化
        if time_str not in time_grouped_data:
            time_grouped_data[time_str] = {
                "x_value": time_str,
                "cages": {}
            }

        # 获取鼠笼号
        cage_number = row['mouse_cage_number']
        cage_name = f"鼠笼{cage_number}"

        # 为该鼠笼创建数据字典
        cage_data = {}

        # 遍历所有列，将有值的数据添加到鼠笼数据中
        for column, value in row.items():
            # 跳过id、鼠笼号、时间等字段，只保留测量数据
            if column in ['id', 'mouse_cage_number', 'epoch_start_time', 'epoch_end_time', 'time', 'remarks']:
                continue

            # 如果值为None或文本则改为nan
            if value is  None or type(value) is str:
                value = np.nan
            # 使用中文列名
            chinese_name = column_mapping.get(column, column)
            cage_data[chinese_name] = value

        # 将鼠笼数据添加到该时间组的总数据中
        time_grouped_data[time_str]["cages"][cage_name] = cage_data

    # 转换为列表格式
    result_list = list(time_grouped_data.values())

    return result_list

#
# # 使用示例
# original_data = {
#     'total_items': 1,
#     'total_pages': 1,
#     'page': 1,
#     'page_size': 100,
#     'columns': ['id', 'mouse_cage_number', 'oxygen_calibration_zero_value', 'oxygen_calibration_span_value',
#                 'mouse_cage_infrared_temp', 'UFC_flow_num', 'reference_flow_num', 'UGC_flow_num_1', 'UGC_air_pressure',
#                 'UGC_CO2_origin_num', 'UGC_CO2_num', 'reference_CO2_num', 'CO2_output_num', 'ZOS_oxygen_origin_num',
#                 'ZOS_oxygen_num', 'reference_oxygen_num', 'oxygen_consumption_num', 'ENM_temperature_num',
#                 'ENM_humidity_num', 'ENM_noise_num', 'ENM_barometer_num', 'ENM_running_wheel_num', 'DWM_weight_num',
#                 'EM_weight_num', 'WM_weight_num', 'epoch_start_time', 'epoch_end_time', 'remarks', 'time'],
#     'rows': [
#         {'id': 1, 'mouse_cage_number': 0, 'oxygen_calibration_zero_value': None, 'oxygen_calibration_span_value': None,
#          'mouse_cage_infrared_temp': None, 'UFC_flow_num': 0, 'reference_flow_num': 0, 'UGC_flow_num_1': None,
#          'UGC_air_pressure': None, 'UGC_CO2_origin_num': None, 'UGC_CO2_num': None, 'reference_CO2_num': None,
#          'CO2_output_num': None, 'ZOS_oxygen_origin_num': None, 'ZOS_oxygen_num': None, 'reference_oxygen_num': None,
#          'oxygen_consumption_num': None, 'ENM_temperature_num': None, 'ENM_humidity_num': None, 'ENM_noise_num': None,
#          'ENM_barometer_num': None, 'ENM_running_wheel_num': None, 'DWM_weight_num': None, 'EM_weight_num': None,
#          'WM_weight_num': None, 'epoch_start_time': '2026-01-07 17:59:51.927',
#          'epoch_end_time': '2026-01-07 18:00:28.471',
#          'remarks': ' UGC_monitor_data_cage_0__remarks: 请求报文03040000000531eb-Time OUT1-未获取到响应数据; ',
#          'time': '2026-01-07 18:05:28.572'},
#         {'id': 1, 'mouse_cage_number': 2, 'oxygen_calibration_zero_value': None, 'oxygen_calibration_span_value': None,
#          'mouse_cage_infrared_temp': None, 'UFC_flow_num': 0, 'reference_flow_num': 0, 'UGC_flow_num_1': None,
#          'UGC_air_pressure': None, 'UGC_CO2_origin_num': None, 'UGC_CO2_num': None, 'reference_CO2_num': None,
#          'CO2_output_num': None, 'ZOS_oxygen_origin_num': None, 'ZOS_oxygen_num': None, 'reference_oxygen_num': None,
#          'oxygen_consumption_num': None, 'ENM_temperature_num': None, 'ENM_humidity_num': None, 'ENM_noise_num': None,
#          'ENM_barometer_num': None, 'ENM_running_wheel_num': None, 'DWM_weight_num': None, 'EM_weight_num': None,
#          'WM_weight_num': None, 'epoch_start_time': '2026-01-07 17:59:51.927',
#          'epoch_end_time': '2026-01-07 18:00:28.471',
#          'remarks': ' UGC_monitor_data_cage_0__remarks: 请求报文03040000000531eb-Time OUT1-未获取到响应数据; ',
#          'time': '2026-01-07 18:03:28.572'},
#         {'id': 1, 'mouse_cage_number': 1, 'oxygen_calibration_zero_value': None, 'oxygen_calibration_span_value': None,
#          'mouse_cage_infrared_temp': None, 'UFC_flow_num': 0, 'reference_flow_num': 0, 'UGC_flow_num_1': None,
#          'UGC_air_pressure': None, 'UGC_CO2_origin_num': None, 'UGC_CO2_num': None, 'reference_CO2_num': None,
#          'CO2_output_num': None, 'ZOS_oxygen_origin_num': None, 'ZOS_oxygen_num': None, 'reference_oxygen_num': None,
#          'oxygen_consumption_num': None, 'ENM_temperature_num': None, 'ENM_humidity_num': None, 'ENM_noise_num': None,
#          'ENM_barometer_num': None, 'ENM_running_wheel_num': None, 'DWM_weight_num': None, 'EM_weight_num': None,
#          'WM_weight_num': None, 'epoch_start_time': '2026-01-07 17:59:51.927',
#          'epoch_end_time': '2026-01-07 18:00:28.471',
#          'remarks': ' UGC_monitor_data_cage_0__remarks: 请求报文03040000000531eb-Time OUT1-未获取到响应数据; ',
#          'time': '2026-01-07 18:03:28.572'}
#     ],
#     'columns_title': ['序号', '鼠笼号', '氧浓度0点校准值', '氧浓传感器span数值', '鼠笼红外温度(°C)',
#                       'ufc_流量计测量值(sccm)', 'ufc_参考气流量计测量值(sccm)', 'ugc_流量计1', '气压(KPa)',
#                       '补偿前CO2(%)', 'CO2(%)', '参考气CO2(%)', 'CO2生产量(%)', '补偿前氧气传感器测量值(%)',
#                       '氧气传感器测量值(%)', '参考气氧气测量值(%)', '耗氧量(%)', '温度测量值(°C)', '湿度测量值(%RH)',
#                       '噪声测量值(dB)', '大气压测量值(KPa)', '当前计量周期内跑轮圈数 测量值', '饮水重量测量值(g)',
#                       '食物重量测量值(g)', '称重重量测量值(g)', '轮次开始时间', '轮次结束时间', '备注', '获取时间']
# }
#
# # 转换数据
# converted_data = convert_data_to_cage_format(original_data)
# print(converted_data)