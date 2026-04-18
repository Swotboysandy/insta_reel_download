import urllib.request, zipfile, io

print('Downloading Inter zip release 4.0...')
req = urllib.request.Request("https://github.com/rsms/inter/releases/download/v4.0/Inter-4.0.zip", headers={'User-Agent': 'Mozilla/5.0'})
try:
    r = urllib.request.urlopen(req)
    with zipfile.ZipFile(io.BytesIO(r.read())) as z:
        found = False
        for finfo in z.infolist():
            if "Inter-SemiBold" in finfo.filename and finfo.filename.endswith(".ttf") and "Italic" not in finfo.filename:
                content = z.read(finfo.filename)
                with open("Inter-SemiBold.ttf", "wb") as f:
                    f.write(content)
                print("Extracted Inter-SemiBold.ttf from", finfo.filename)
                found = True
                break
        if not found:
            print("Not found in ZIP. Files:", z.namelist()[:20])
except Exception as e:
    print("Download failed:", e)
