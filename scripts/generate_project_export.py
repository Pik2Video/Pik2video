# scripts/generate_project_export.py
import os
import re
from pathlib import Path

class ProjectExporter:
    def __init__(self, src_dir="src"):
        self.src_dir = Path(src_dir)
        self.output_dir = Path("export")
        self.output_dir.mkdir(exist_ok=True)
    
    def export_full_code(self):
        """Основной экспорт - весь код без комментариев"""
        output = self.output_dir / "PROJECT_CODE.txt"
        with open(output, "w", encoding="utf-8") as out:
            for py_file in sorted(self.src_dir.rglob("*.py")):
                if "__pycache__" in str(py_file):
                    continue
                
                out.write(f"\n{'='*70}\n")
                out.write(f"# {py_file}\n")
                out.write(f"{'='*70}\n\n")
                
                content = py_file.read_text(encoding="utf-8")
                # Удаляем комментарии (только на русском)
                content = self.remove_russian_comments(content)
                out.write(content)
                out.write("\n")
    
    def export_structure(self):
        """Экспорт структуры проекта (дерево)"""
        output = self.output_dir / "PROJECT_STRUCTURE.txt"
        with open(output, "w", encoding="utf-8") as out:
            for root, dirs, files in os.walk(self.src_dir):
                level = root.replace(str(self.src_dir), "").count(os.sep)
                indent = " " * 4 * level
                out.write(f"{indent}{os.path.basename(root)}/\n")
                subindent = " " * 4 * (level + 1)
                for file in sorted(files):
                    if file.endswith(".py"):
                        out.write(f"{subindent}{file}\n")
    
    def export_imports(self):
        """Экспорт всех импортов"""
        output = self.output_dir / "PROJECT_IMPORTS.txt"
        with open(output, "w", encoding="utf-8") as out:
            for py_file in sorted(self.src_dir.rglob("*.py")):
                if "__pycache__" in str(py_file):
                    continue
                content = py_file.read_text(encoding="utf-8")

                imports = [m.group(0) for m in re.finditer(r'^(from|import)\s+.+$', content, re.MULTILINE)]

                #imports = re.findall(r'^(from|import)\s+.+$', content, re.MULTILINE)
                if imports:
                    out.write(f"\n# {py_file}\n")
                    out.write("\n".join(imports))
                    out.write("\n")
    
    def remove_russian_comments(self, content):
        lines = []
        for line in content.split('\n'):
            stripped = line.lstrip()
            # Если строка является однострочным комментарием
            if stripped.startswith('#'):
                # Проверяем, есть ли русские буквы в комментарии
                if re.search('[а-яА-ЯёЁ]', stripped):
                    continue  # удаляем строку целиком
            lines.append(line)
        return '\n'.join(lines)
    
    def run(self):
        print("📁 Экспорт структуры...")
        self.export_structure()
        
        print("📄 Экспорт кода без комментариев...")
        self.export_full_code()
        
        print("📦 Экспорт импортов...")
        self.export_imports()
        
        print(f"✅ Готово! Файлы сохранены в папке {self.output_dir}")

if __name__ == "__main__":
    exporter = ProjectExporter()
    exporter.run()