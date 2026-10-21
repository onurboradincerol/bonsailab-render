"""Exhaustive 5%-grid search in bounded NumPy batches; no candidate sampling."""
import itertools,time
import numpy as np

def search(c,mats,sp,t,inv,modes):
 if any(mode not in ('technical','economical') for mode in modes):raise c.InputError('Geçersiz tasarım modu.')
 start=time.perf_counter();r=c.RULES;step=r['grid_step'];total=100//step
 mats=sorted(mats,key=lambda m:m['name']);states=[];v=[]
 refs={mode:c.reference_mix(sp,inv,mode) for mode in modes}
 norms={mode:sum(x*x for x in ref.values()) for mode,ref in refs.items()}
 for m in mats:
  prepared=c.prepare_material(m,inv[m['name']]);state=c.component_state(prepared,t['height']);states.append(state)
  fit=c.grain_fit(m,inv[m['name']],t)
  v.append([state['cc'],state['tp'],prepared['ph'],fit or 0,int(m['name'] in c.PRIMARY),int(m['kind']!='Mineral granül'),int(m['name'] in c.ADDONS),int(m['name'] in c.ACID),.65*c.base_material_preference(m,sp,t)+(1.1*(1-fit) if fit is not None else 0),int(m['grain_applicable']),prepared['numeric_estimation']['relative_buffer']])
 vectors=np.asarray(v,dtype=float);best={mode:None for mode in modes};count=0
 physical_counts={mode:0 for mode in modes};ph_counts={mode:0 for mode in modes}
 a=r['acceptance'];acid=sp['group']=='Asidik';cc_floor=max(a['min_cc_floor'],t['target_cc_max']-a['max_cc_deficit']);afp_floor=max(a['min_afp_floor'],t['target_afp_max']-a['max_afp_deficit'])
 primary_min=r['primary_min'].get(sp['group'],r['primary_min']['default'])/step
 organic_max=r['organic_max'].get(sp['group'],r['organic_max']['default'])/step
 # Small source-model lookup tables are reused across all material combinations.
 # Each table depends only on that model's own participants and their shares.
 model_tables={}
 def correction_table(block,indexes):
  mid,local,source=block;global_ids=tuple(indexes[i] if i>=0 else -1 for i in local);key=(mid,global_ids)
  if key in model_tables:return model_tables[key]
  shape=tuple(total+1 if i>=0 else 1 for i in global_ids)
  delta=np.zeros(shape+(2,),dtype=float)
  model_states=[states[i] if i>=0 else {} for i in global_ids]
  remapped=(mid,tuple(j if i>=0 else -1 for j,i in enumerate(global_ids)),source)
  ranges=[range(1,total+1) if i>=0 else (0,) for i in global_ids]
  for units in itertools.product(*ranges):
   if sum(units)>total:continue
   weights=[u*step for u in units]
   pred=c.physics._prediction(remapped,weights,model_states,t['height'])
   for j,field in enumerate(('cc','tp')):
    delta[units+(j,)]=pred[field]*sum(weights)/100-sum(w*state[field]/100 for w,state in zip(weights,model_states) if w)
  model_tables[key]=delta;return delta
 for k in range(1,min(t['max_components'],len(mats))+1):
  grid=np.asarray(list(c.distributions(total,(total,)*k)),dtype=np.int16)
  for indexes in itertools.combinations(range(len(mats)),k):
   items=tuple(mats[i] for i in indexes);vs=vectors[list(indexes)];caps=np.asarray([c.cap_for(m,sp)//step for m in items])
   if caps.sum()<total or sum(cap*row[4] for cap,row in zip(caps,vs))<primary_min:continue
   if acid and sum(cap*row[7] for cap,row in zip(caps,vs))<r['acid_min']/step:continue
   # Ordered accumulation mirrors public evaluation; BLAS threads are unnecessary.
   def weighted(units,column):
    out=np.zeros(len(units))
    for j in range(k):out+=units[:,j]*vs[j,column]
    return out
   valid=np.all(grid<=caps,axis=1)
   valid &= weighted(grid,4)>=primary_min
   valid &= weighted(grid,5)<=organic_max
   valid &= weighted(grid,6)<=r['addon_max']/step
   if acid:valid &= weighted(grid,7)>=r['acid_min']/step
   units=grid[valid]
   if not len(units):continue
   count+=len(units);cc=weighted(units,0)/total;tp=weighted(units,1)/total
   blocks=c.physics.eligible_blocks(items,inv)
   if blocks:
    support_total=np.zeros(len(units));cc_delta=np.zeros(len(units));tp_delta=np.zeros(len(units))
    for block in blocks:
     local=block[1];table=correction_table(block,indexes)
     coordinates=tuple(units[:,i] if i>=0 else np.zeros(len(units),dtype=int) for i in local)
     delta=table[coordinates];support=coordinates[0]*sum(coordinates[1:])
     support_total+=support;cc_delta+=support*delta[:,0];tp_delta+=support*delta[:,1]
    cc+=cc_delta/support_total;tp+=tp_delta/support_total
   cc=np.clip(cc,0,tp);afp=tp-cc
   numerator=np.zeros(len(units))
   for j in range(k):numerator+=units[:,j]*vs[j,2]*vs[j,10]
   ph=numerator/weighted(units,10)
   sized=weighted(units,9);fit=np.divide(weighted(units,3),sized,out=np.full(len(units),np.nan),where=sized!=0)
   failures=(cc<cc_floor-1e-9).astype(int)+(afp<afp_floor-1e-9)+(np.isfinite(fit)&(fit<a['min_grain_overlap']-1e-9))
   conditional=(acid or bool(t['environment_warnings'])) | ~np.isfinite(fit) | (fit<a['conditional_grain_overlap']-1e-9) | (cc<t['target_cc_max']-a['conditional_target_deficit']-1e-9) | (afp<t['target_afp_max']-a['conditional_target_deficit']-1e-9)
   tier=np.where(failures,2,np.where(conditional,1,0))
   s=r['score'];score=2*(np.maximum(0,t['target_cc_max']-cc-2)/9)**2+s['cc_excess_weight']*(np.maximum(0,cc-t['target_cc_max']-s['cc_excess_tolerance'])/9)**2
   score+=2.6*(np.maximum(0,t['target_afp_max']-afp-2)/9)**2+s['afp_excess_weight']*(np.maximum(0,afp-t['target_afp_max']-s['afp_excess_tolerance'])/9)**2
   score+=weighted(units,8)/total
   if any(m['name'] in c.ADDONS-{'Vermikülit'} for m in items):score+=.85
   distance=np.maximum(0,np.maximum(sp['ph_min']-ph,ph-sp['ph_max']));distance[distance<=1e-9]=0
   distance=np.round(distance,9);in_band=(ph>=sp['ph_min']-1e-9)&(ph<=sp['ph_max']+1e-9)
   for mode in modes:
    if mode=='economical' and any(not c.easy_stock(m,inv) for m in items):continue
    sc=score.copy()
    if refs[mode]:
     refdot=np.zeros(len(units))
     for j,m in enumerate(items):refdot+=units[:,j]*refs[mode].get(m['name'],0)
     sc+=s['reference_weight']*(np.sum(units.astype(float)**2,axis=1)/(total**2)+norms[mode]-2*refdot/total)
    physical_counts[mode]+=int(np.count_nonzero(failures==0));ph_counts[mode]+=int(np.count_nonzero((failures==0)&in_band))
    rounded=np.round(sc,9)
    # Lexicographic filtering keeps the same rank keys, and the original grid's
    # ascending share order resolves exact ties within a fixed material tuple.
    candidates=np.arange(len(units))
    for key in ((failures>0).astype(int),failures,(distance>0).astype(int),distance,tier,rounded):
     values=key[candidates];candidates=candidates[values==values.min()]
     if len(candidates)==1:break
    i=int(candidates[0]);shares=tuple(int(u)*step for u in units[i])
    rank=c.selection_rank(int(tier[i]),int(failures[i]),float(ph[i]),sp,float(sc[i]),items,shares)
    if best[mode] is None or rank<best[mode][0]:best[mode]=(rank,items,shares)
 results={}
 for mode,winner in best.items():
  if winner is None:results[mode]=None;continue
  rank,items,shares=winner;score,est=c.evaluate(items,shares,sp,t,inv,mode)
  public_rank=c.candidate_rank(items,shares,sp,t,inv,score,est,mode)
  assert rank==public_rank,(rank,public_rank)
  results[mode]=(public_rank,score,items,shares,est,c.viability(items,shares,sp,t,inv,est))
 return results,{'complete':True,'ph_selection':{mode:{'physical_feasible_candidates':physical_counts[mode],'ph_feasible_candidates':ph_counts[mode],'ph_band':[sp['ph_min'],sp['ph_max']],'basis':'Fiziksel asgari koşulları sağlayan adaylar arasında önce tahmini pH bandı; yoksa banda en yakın tahmin.'} for mode in modes},'candidate_count':count,'max_components':t['max_components'],'step_percent':step,'material_count':len(mats),'seconds':round(time.perf_counter()-start,4),'scope':f'Yalnız seçili stok, 1–{t["max_components"]} bileşen ve %{step} adım; bu sonlu alanda tam tarama.','method':'BATCHED_EXHAUSTIVE_GRID'}
