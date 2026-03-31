import argparse
import os
import shutil
import re
import fnmatch

def is_text_file(file_path):
    try:
        # Try opening the file in text mode and reading the first chunk
        with open(file_path, 'r', encoding='utf-8') as file:
            file.read(1024)  # Read first 1KB of the file
        return True
    except UnicodeDecodeError:
        # If a UnicodeDecodeError occurs, it's likely not a text file
        return False

def replace_in_file(file_path, old_words, new_words):
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            content = file.read()

        for old, new in zip(old_words, new_words):
            content = re.sub(old, new, content)

        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(content)
    except UnicodeDecodeError:
        print(f"Warning: UnicodeDecodeError encountered in file {file_path}. File skipped.")

def rename_files_and_dirs(root_dir, old_words, new_words, exclude_folders):
    for dirpath, dirnames, filenames in os.walk(root_dir, topdown=False):
        if any(path_str in dirpath for path_str in exclude_folders):
            continue
        
        # Rename files
        for filename in filenames:
            new_name = filename
            for old, new in zip(old_words, new_words):
                new_name = re.sub(old, new, new_name)

            if new_name != filename:
                os.rename(os.path.join(dirpath, filename), os.path.join(dirpath, new_name))

        # Rename directories
        for dirname in dirnames:
            new_name = dirname
            for old, new in zip(old_words, new_words):
                new_name = re.sub(old, new, new_name)

            if new_name != dirname:
                os.rename(os.path.join(dirpath, dirname), os.path.join(dirpath, new_name))

def replace_contents(root_dir, old_words, new_words, exclude_folders):
    for dirpath, _, filenames in os.walk(root_dir):
        if any(path_str in dirpath for path_str in exclude_folders):
            continue
        
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if is_text_file(file_path):
                replace_in_file(file_path, old_words, new_words)

def custom_ignore_patterns(directory, patterns):
    def _ignore_patterns(path, names):
        ignored_names = []
        for pattern in patterns:
            pattern_path = os.path.join(directory, pattern)
            for name in names:
                full_path = os.path.join(path, name)
                if os.path.isdir(full_path):
                    full_path += '/'
                if fnmatch.fnmatch(full_path, pattern_path):
                    ignored_names.append(name)
        return set(ignored_names)
    return _ignore_patterns

def main():
    parser = argparse.ArgumentParser(description='Clone and replace words in project directories.')
    parser.add_argument('--dir', required=True, help='Directory to clone')
    parser.add_argument('--destDir', required=True, help='Directory to clone to')
    parser.add_argument('--oldWords', required=True, help='Comma-separated list of words to replace')
    parser.add_argument('--newWords', required=True, help='Comma-separated list of new words')
    parser.add_argument('--destDirName', required=True, help='Name of new project directory')
    
    args = parser.parse_args()

    src_dir = args.dir
    dest_dir = os.path.join(args.destDir, args.destDirName)
    # dest_dir = os.path.join(os.path.dirname(src_dir), args.destDirName)
    old_words = args.oldWords.split(',')
    new_words = args.newWords.split(',')
    exclude_folders = ['Pods']

    if len(old_words) != len(new_words):
        print("Error: The number of old words and new words must be equal.")
        return
    
    patterns = ['*Pods*', '*build/outputs*', '*iOS/build*', '*xcworkspace*', '*.idea*']
    shutil.copytree(src_dir, dest_dir, ignore=custom_ignore_patterns(src_dir, patterns))
    rename_files_and_dirs(dest_dir, old_words, new_words, exclude_folders)
    replace_contents(dest_dir, old_words, new_words, exclude_folders)
    print(f"Project cloned and processed successfully to {dest_dir}")

if __name__ == "__main__":
    main()
