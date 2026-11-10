import sys, json, csv, argparse, re, datetime
from html.parser import HTMLParser

# Marmalade's compact prototype notebook entry.
# No external libs. Designed for small local files (CSV/HTML/JSON) containing pose-like records.

SCHEMA = {
    "fields": ["timestamp","module_id","x","y","z","qx","qy","qz","qw","source"]
}

class TableHTMLParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_table = False
        self.in_td = False
        self.rows = []
        self.current = []
    def handle_starttag(self, tag, attrs):
        if tag.lower() == 'table':
            self.in_table = True
        if self.in_table and tag.lower() in ('td','th'):
            self.in_td = True
    def handle_endtag(self, tag):
        if tag.lower() == 'table':
            self.in_table = False
        if self.in_table and tag.lower() in ('td','th'):
            self.in_td = False
        if tag.lower()=='tr' and self.current:
            self.rows.append([c.strip() for c in self.current])
            self.current = []
    def handle_data(self, data):
        if self.in_td:
            self.current.append(data)

def parse_csv(path):
    with open(path, newline='') as f:
        reader = csv.DictReader(f)
        for r in reader:
            yield r

def parse_html_table(path):
    p = TableHTMLParser()
    with open(path) as f:
        p.feed(f.read())
    if not p.rows:
        return
    header = [h.lower() for h in p.rows[0]]
    for row in p.rows[1:]:
        d = {header[i]: row[i] if i < len(row) else '' for i in range(len(header))}
        yield d

def parse_embedded_json(path):
    with open(path) as f:
        data = json.load(f)
    # Try obvious shapes: list of records, or {records: [...]}
    if isinstance(data, list):
        for r in data:
            yield r
    elif isinstance(data, dict):
        for k in ('records','data','poses'):
            if k in data and isinstance(data[k], list):
                for r in data[k]:
                    yield r
        # Fall back: top-level dict interpreted as single record
        if all(isinstance(v,(str,int,float)) for v in data.values()):
            yield data

def normalize_record(rec, source_label):
    # Goal: produce fields in SCHEMA
    out = {f: '' for f in SCHEMA['fields']}
    out['source'] = source_label
    # Timestamp: accept keys 't','timestamp','time'
    for k in ('timestamp','time','t'):
        if k in rec:
            out['timestamp'] = str(rec[k])
            break
    # Module id
    for k in ('module_id','id','name'):
        if k in rec:
            out['module_id'] = str(rec[k]); break
    # Position: accept x,y,z or pos as list
    if all(k in rec for k in ('x','y','z')):
        out['x'] = str(rec['x']); out['y']=str(rec['y']); out['z']=str(rec['z'])
    elif 'pos' in rec and isinstance(rec['pos'], (list,tuple)) and len(rec['pos'])>=3:
        out['x'],out['y'],out['z'] = map(str, rec['pos'][:3])
    # Orientation: accept qx,qy,qz,qw or quat list or euler (marked)
    if all(k in rec for k in ('qx','qy','qz','qw')):
        out.update({k:str(rec[k]) for k in ('qx','qy','qz','qw')})
    elif 'quat' in rec and isinstance(rec['quat'], (list,tuple)) and len(rec['quat'])==4:
        out['qx'],out['qy'],out['qz'],out['qw'] = map(str, rec['quat'])
    elif all(k in rec for k in ('roll','pitch','yaw')):
        # flag: Euler angles present; store as empty quaternion and note in source
        out['qx']=out['qy']=out['qz']=out['qw']=''
        out['source'] += ' (euler:rpy)'
    return out

def validate_and_write(records, base='normalized'):
    rows = list(records)
    problems = []
    # Check timestamps and quaternion presence
    seen_ts = 0
    for i,r in enumerate(rows):
        if not r.get('timestamp'):
            problems.append(f"row {i} missing timestamp")
        else:
            seen_ts +=1
        qfields = [r.get(k) for k in ('qx','qy','qz','qw')]
        if any(qfields) and not all(qfields):
            problems.append(f"row {i} has partial quaternion")
        if 'euler' in r.get('source',''):
            problems.append(f"row {i} uses Euler angles (source notes) - needs conversion")
    # Write CSV
    csv_path = base + '.csv'
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=SCHEMA['fields'])
        writer.writeheader()
        for r in rows:
            writer.writerow(r)
    # Write JSON
    json_path = base + '.json'
    with open(json_path,'w') as f:
        json.dump({'schema':SCHEMA,'records':rows}, f, indent=2)
    # Provenance
    prov = {
        'generated': datetime.datetime.utcnow().isoformat()+'Z',
        'count': len(rows),
        'timestamp_present': seen_ts,
        'problems': problems
    }
    prov_path = base + '_provenance.json'
    with open(prov_path,'w') as f:
        json.dump(prov, f, indent=2)
    print('Wrote', csv_path, json_path, prov_path)
    if problems:
        print('Validation problems:')
        for p in problems[:20]:
            print(' -', p)

def load_adapter(kind, path):
    if kind=='csv':
        return parse_csv(path)
    if kind=='html':
        return parse_html_table(path)
    if kind=='json':
        return parse_embedded_json(path)
    raise ValueError('unknown source type')

def main():
    p = argparse.ArgumentParser(description='PoseHarvest-and-Normalize (prototype)')
    p.add_argument('--source-type', required=True, choices=['csv','html','json'])
    p.add_argument('--source-path', required=True)
    p.add_argument('--out', default='normalized')
    args = p.parse_args()
    adapter = load_adapter(args.source_type, args.source_path)
    normalized = []
    for raw in adapter:
        # raw may have string keys and values; try to coerce JSON-like strings
        # Quick numeric coercion
        reco = {}
        for k,v in raw.items():
            if isinstance(v,str):
                s=v.strip()
                # try JSON value
                try:
                    reco[k]=json.loads(s)
                    continue
                except Exception:
                    pass
                # try numeric
                if re.match(r'^[+-]?\d+\.?\d*$', s):
                    if '.' in s:
                        reco[k]=float(s)
                    else:
                        reco[k]=int(s)
                else:
                    reco[k]=s
            else:
                reco[k]=v
        nr = normalize_record(reco, source_label=args.source_path)
        normalized.append(nr)
    validate_and_write(normalized, base=args.out)

if __name__=='__main__':
    main()
