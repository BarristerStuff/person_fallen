from __future__ import annotations

def area(b): return max(0.0,b[2]-b[0])*max(0.0,b[3]-b[1])
def inter(a,b): return max(0.0,min(a[2],b[2])-max(a[0],b[0]))*max(0.0,min(a[3],b[3])-max(a[1],b[1]))
def center(b): return ((b[0]+b[2])/2,(b[1]+b[3])/2)
def expand(b,frac=.35):
 w=b[2]-b[0];h=b[3]-b[1];return [b[0]-frac*w,b[1]-frac*h,b[2]+frac*w,b[3]+frac*h]
def inside(pt,b): return b[0]<=pt[0]<=b[2] and b[1]<=pt[1]<=b[3]
def metrics(det,p2):
 i=inter(det,p2); ad=area(det); ap=area(p2); u=ad+ap-i
 return {'iou':i/u if u else 0.0,'intersection_over_min_area':i/min(ad,ap) if min(ad,ap) else 0.0,'detector_center_inside_expanded_p2':inside(center(det),expand(p2)),'p2_center_inside_expanded_detector':inside(center(p2),expand(det)),'normalized_center_distance':(((center(det)[0]-center(p2)[0])**2+(center(det)[1]-center(p2)[1])**2)**.5)/max(1.0,(ad**.5+ap**.5)/2)}
def match(detectors,p2_boxes):
 pairs=[]
 for i,d in enumerate(detectors):
  for j,p in enumerate(p2_boxes):
   m=metrics(d,p); ok=m['iou']>=.15 or m['intersection_over_min_area']>=.50 or m['detector_center_inside_expanded_p2'] or m['p2_center_inside_expanded_detector']
   if ok:
    score=(m['iou'],m['intersection_over_min_area'],int(m['p2_center_inside_expanded_detector']),int(m['detector_center_inside_expanded_p2']),-m['normalized_center_distance'],-i,-j)
    pairs.append((score,i,j,m))
 pairs.sort(reverse=True); used_d=set();used_p=set();out=[]
 for score,i,j,m in pairs:
  if i not in used_d and j not in used_p:
   used_d.add(i);used_p.add(j);out.append({'detector_index':i,'p2_index':j,'score':score,'metrics':m})
 return sorted(out,key=lambda x:x['detector_index'])
