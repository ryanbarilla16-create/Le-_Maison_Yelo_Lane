import os

for root, dirs, files in os.walk('templates'):
    for file in files:
        if file.endswith('.html'):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except UnicodeDecodeError:
                continue

            new_content = content.replace('<img ', '<img loading="lazy" decoding="async" ')
            new_content = new_content.replace('loading="lazy" decoding="async" loading="lazy" decoding="async" ', 'loading="lazy" decoding="async" ')
            new_content = new_content.replace('loading="lazy" decoding="async" loading="lazy" ', 'loading="lazy" decoding="async" ')

            if new_content != content:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f'Patched {filepath}')
