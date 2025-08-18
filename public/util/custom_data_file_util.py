"""
自定义文件的创建和解析
将文件夹全部转成一个文件格式
"""
import base64
import json
import os

import pandas as pd

from public.function.Tansfer.DbTransferExcel import DbTransferExcel
from public.util.folder_util import folder_util
class custom_template_file_util:
    """自定义模板文件"""
    encoding = "utf-8-sig"
    extension_name = "template"
    db_extension_name="db"
    pass
    @classmethod
    def save_template_contents_as_custom_file(cls,db_file_path):
        content=None
        with open(db_file_path, 'rb') as f:
            #将二进制内容编码为 Base64 的字符串
            content = base64.b64encode(f.read()).decode(cls.encoding)  #  转成base64字符串格式

        # 获取上层路径
        parent_directory = os.path.dirname(db_file_path)
        folder_name = os.path.basename(db_file_path)
        # 分离扩展名
        file_name_without_extension, _ = os.path.splitext(folder_name)
        custom_file_path = os.path.join(parent_directory, f'{file_name_without_extension}.{cls.extension_name}')
        # 将内容写入自定义格式文件
        with open(custom_file_path, 'w', encoding=cls.encoding) as custom_file:
            json.dump(content, custom_file, ensure_ascii=False, indent=4)
        #删除该DB文件
        # 检查文件是否存在
        if os.path.isfile(db_file_path):
            os.remove(db_file_path)  # 删除文件
        return custom_file_path
    @classmethod
    def load_template_contents_from_custom_file(cls,custom_file_path):
        # 读取自定义格式文件
        with open(custom_file_path, 'r', encoding=cls.encoding) as custom_file:
            content = json.load(custom_file)

        # 获取文件所在的文件夹路径
        folder_path = os.path.dirname(custom_file_path)
        # 从路径中获取文件名（带扩展名）
        file_name_with_extension = os.path.basename(custom_file_path)
        # 分离扩展名
        file_name_without_extension, _ = os.path.splitext(file_name_with_extension)
        target_file = os.path.join(folder_path, f"{file_name_without_extension}.{cls.db_extension_name}")

        # 将内容写入文件
        with open(target_file, 'wb') as f:
            f.write(base64.b64decode(content))
        return target_file
    @classmethod
    def get_db_extension_file(cls,file_path):
        # 获取文件所在的文件夹路径
        folder_path = os.path.dirname(file_path)
        # 从路径中获取文件名（带扩展名）
        file_name_with_extension = os.path.basename(file_path)
        # 分离扩展名
        file_name_without_extension, _ = os.path.splitext(file_name_with_extension)
        return os.path.join(folder_path, f"{file_name_without_extension}.{cls.db_extension_name}")

    @classmethod
    def get_template_extension_file(cls, file_path):
        # 获取文件所在的文件夹路径
        folder_path = os.path.dirname(file_path)
        # 从路径中获取文件名（带扩展名）
        file_name_with_extension = os.path.basename(file_path)
        # 分离扩展名
        file_name_without_extension, _ = os.path.splitext(file_name_with_extension)
        return os.path.join(folder_path, f"{file_name_without_extension}.{cls.extension_name}")
class custom_data_file_util:
    """自定义数据文件"""
    encoding = "utf-8-sig"
    extension_name = "Mdata"
    @classmethod
    def save_folder_contents_as_custom_file(cls,folder_path):
        contents = {}

        # 遍历文件夹
        for root, _, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                # 读取文件内容
                with open(file_path, 'rb') as f:
                    #将二进制内容编码为 Base64 的字符串
                    contents[os.path.relpath(file_path, folder_path)] = base64.b64encode(f.read()).decode(cls.encoding)  #  转成base64字符串格式

        # 获取上层路径
        parent_directory = os.path.dirname(folder_path)
        folder_name = os.path.basename(folder_path)
        custom_file_path = os.path.join(parent_directory, f'{folder_name}.{cls.extension_name}')
        # 将内容写入自定义格式文件
        with open(custom_file_path, 'w', encoding=cls.encoding) as custom_file:
            json.dump(contents, custom_file, ensure_ascii=False, indent=4)

        #将数据db文件转成excel文件
        transfer_handle =DbTransferExcel()
        excel_file_path = os.path.join(parent_directory, f'{folder_name}.xlsx')
        used_sheet_names = set()
        with pd.ExcelWriter(excel_file_path, engine="openpyxl") as writer:
            transfer_handle.export_db_to_excel( writer, combine_mode=True, sheet_used=used_sheet_names, chunksize=(5000 or None))
        #删除该文件夹
        folder_util.remove_non_empty_folder(folder_path)
    def load_folder_contents_from_custom_file(cls,custom_file_path):
        # 读取自定义格式文件
        with open(custom_file_path, 'r', encoding=cls.encoding) as custom_file:
            contents = json.load(custom_file)

        # 获取文件所在的文件夹路径
        folder_path = os.path.dirname(custom_file_path)
        # 从路径中获取文件名（带扩展名）
        file_name_with_extension = os.path.basename(custom_file_path)
        # 分离扩展名
        file_name_without_extension, _ = os.path.splitext(file_name_with_extension)
        target_folder = os.path.join(folder_path, file_name_without_extension)
        # 将内容写入指定文件夹
        for relative_path, content in contents.items():
            # 创建目标文件夹（如果不存在）
            target_file_path = os.path.join(target_folder, relative_path)
            os.makedirs(os.path.dirname(target_file_path), exist_ok=True)
            # 将内容写入文件
            with open(target_file_path, 'wb') as f:
                f.write(base64.b64decode(content))