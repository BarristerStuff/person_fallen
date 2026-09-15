import csv,json,hashlib,os,sys
from pathlib import Path
from ultralytics import YOLO
BASE=Path('/home/yanbo/net_vlm_person_fallen_v2_optimization/25_person_fallen_v7_a0_geometry_verifier')
manifest=BASE/'manifests/full_combined436.csv'; out=BASE/'detector/persons_full_dev.csv'
det=YOLO(str(BASE.parent/'13_person_fallen_v4_pose_attributes/assets/person_detector/yolo11n.pt'))
pose=YOLO(str(BASE/'detector/yolo11n-pose.pt'))
rows=list(csv.DictReader(open(manifest)))
def iou(a,b):
 x1=max(a[0],b[0]);y1=max(a[1],b[1]);x2=min(a[2],b[2]);y2=min(a[3],b[3]); inter=max(0,x2-x1)*max(0,y2-y1); aa=(a[2]-a[0])*(a[3]-a[1]);bb=(b[2]-b[0])*(b[3]-b[1]);return inter/(aa+bb-inter+1e-9)
with open(out,'w',newline='') as f:
 w=csv.writer(f);w.writerow(['item_id','image_sha256','person_idx','conf','x1','y1','x2','y2','area_ratio','level','kp_json'])
 for n,r in enumerate(rows,1):
  p=r['image_path']; im=det.predict(p,verbose=False,conf=.15,classes=[0])[0]; orig=im.orig_shape; H,W=orig
  boxes=[]
  for b in im.boxes:
   x1,y1,x2,y2=map(float,b.xyxy[0]); ar=(x2-x1)*(y2-y1)/(W*H)
   if ar>=.002: boxes.append((x1,y1,x2,y2,float(b.conf[0])))
  po=pose.predict(p,verbose=False,conf=.05,classes=[0])[0]; pb=[]; 
  if po.boxes is not None:
   for i,b in enumerate(po.boxes): pb.append((list(map(float,b.xyxy[0])),po.keypoints.data[i].cpu().tolist()))
  for j,(x1,y1,x2,y2,c) in enumerate(boxes):
   matches=[(iou((x1,y1,x2,y2),b),kp) for b,kp in pb]; kp=max(matches,key=lambda x:x[0])[1] if matches and max(matches)[0]>.1 else []
   w.writerow([r['item_id'],r['image_sha256'],j,c,x1,y1,x2,y2,(x2-x1)*(y2-y1)/(W*H),'primary' if (x2-x1)*(y2-y1)/(W*H)>=.01 else 'background',json.dumps(kp,separators=(',',':'))])
  if n%20==0: print(n,file=sys.stderr)
