import urllib.request
req = urllib.request.Request('https://minimal-voice-loop2-2.onrender.com/api/phone/incoming-call')
with urllib.request.urlopen(req, timeout=20) as r:
    print(r.status)
    print(r.read().decode('utf-8', 'ignore'))
