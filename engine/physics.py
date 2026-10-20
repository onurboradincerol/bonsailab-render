"""Source curve transfer, hydrostatic capacity and in-domain mixture interpolation.

No third-party runtime dependencies. Percentages are volume percentages;
pressure head is cm water. All inferred/transfer operations are labelled.
"""
from functools import lru_cache
import itertools,json,math
from pathlib import Path
SCIENCE=json.loads((Path(__file__).parent/'data/database.json').read_text(encoding='utf-8'))['mixture_science']

def theta(curve,h):
    h=max(0.,float(h));r=curve['theta_r'];s=curve['theta_s'];n=curve['n']
    if curve['kind']=='vg':return r+(s-r)/(1+(curve['alpha_cm_inv']*h)**n)**(1-1/n)
    if curve['kind']=='log_logistic':return r+(s-r)/(1+(h/curve['x0_cm'])**n)
    raise ValueError('Unknown retention curve')

def capacity(curve,height,steps=128):
    """Integral mean, constant area, free drainage with water table at base."""
    if height<=0 or steps%2 or steps<2:raise ValueError('Positive height and even integration steps required')
    dx=height/steps
    return (theta(curve,0)+theta(curve,height)+sum((4 if i%2 else 2)*theta(curve,i*dx) for i in range(1,steps)))/(3*steps)*100

@lru_cache(maxsize=1024)
def fitted_lambda(tp,cc,pwp,ref_height):
    """Fit a simple exponential shape to container CC; shape is an assumption."""
    lo,hi=1e-8,1e7
    for _ in range(70):
        lam=(lo+hi)/2
        mean=pwp+(tp-pwp)*(-math.expm1(-ref_height/lam))*lam/ref_height
        if mean<cc:lo=lam
        else:hi=lam
    return (lo+hi)/2

@lru_cache(maxsize=256)
def pure_state(name,height):
    pure=SCIENCE['pure_curves'][name];curve=pure['curve'];ref_height=SCIENCE['reference_height_cm']
    cc=capacity(curve,height);ref_cc=capacity(curve,ref_height)
    return {'cc':cc,'tp':curve['theta_s']*100,'reference_cc':ref_cc,'height_delta':cc-ref_cc,'basis':'LITERATURE_TRANSFER','source':pure['source'],'curve':curve,'pwp':pure.get('unavailable_water',0)*100 if 'unavailable_water' in pure else None,'density':pure.get('density')}

def material_state(m,height):
    cc=m['tp']*m['cc']/max(1e-12,m['cc']+m['afp']);tp=m['tp'];ref_cc=cc
    pure=SCIENCE['pure_curves'].get(m['name'])
    if pure:
        return dict(pure_state(m['name'],height))
    profile=m.get('reference_used') or m.get('physical_reference')
    if profile and m.get('awc') is not None and 0<cc<tp:
        pwp=max(0,cc-m['awc']);ref_height=profile['reference_height_cm'];lam=fitted_lambda(tp,cc,pwp,ref_height)
        current=pwp+(tp-pwp)*(-math.expm1(-height/lam))*lam/height
        return {'cc':current,'tp':tp,'reference_cc':cc,'height_delta':current-cc,'basis':'ESTIMATED_REFERENCE_CURVE' if profile.get('method')=='REFERENCE_CC_AWC_EXPONENTIAL' else 'CALIBRATED_SHAPE_ASSUMPTION','source':profile.get('source','EST28'),'curve':{'kind':'fitted_exponential','lambda_cm':lam,'pwp':pwp,'reference_height_cm':ref_height},'pwp':pwp}
    return {'cc':cc,'tp':tp,'reference_cc':cc,'height_delta':0.,'basis':'LEGACY_ASSUMPTION','source':None,'curve':None}

def bracket(axis,x):
    if x<axis[0]-1e-10 or x>axis[-1]+1e-10:return None
    x=max(axis[0],min(axis[-1],x))
    for i in range(len(axis)-1):
        if x<=axis[i+1]+1e-12:return i,(x-axis[i])/(axis[i+1]-axis[i])
    return len(axis)-2,1.

@lru_cache(maxsize=128)
def node_states(model_id,height):
    model=next((m for m in SCIENCE['binary']+[SCIENCE['ternary']] if m['id']==model_id),None)
    if model is None:raise ValueError('Unknown mixture model')
    return tuple((capacity(curve,height),curve['theta_s']*100) for curve in model['curves'])

def mix_curve_state(model_id,shares,height):
    """Measured-domain interpolator only; endpoint bridges are labelled separately."""
    binary=next((m for m in SCIENCE['binary'] if m['id']==model_id),None)
    if len(shares)!=(2 if binary else 3) or any(not math.isfinite(x) or x<0 for x in shares) or sum(shares)<=0:raise ValueError('Invalid mixture shares')
    nodes=node_states(model_id,height);total=sum(shares)
    if binary:
        b=bracket(binary['fractions'],shares[1]/total)
        if b is None:return None
        i,w=b;return tuple(nodes[i][k]*(1-w)+nodes[i+1][k]*w for k in (0,1))
    axis=SCIENCE['ternary']['axis'];bp=bracket(axis,shares[1]/total);bq=bracket(axis,shares[2]/total)
    if bp is None or bq is None:return None
    i,u=bp;j,v=bq;n=len(axis)
    return tuple(nodes[i*n+j][k]*(1-u)*(1-v)+nodes[(i+1)*n+j][k]*u*(1-v)+nodes[i*n+j+1][k]*(1-u)*v+nodes[(i+1)*n+j+1][k]*u*v for k in (0,1))

def eligible_blocks(items,stocks):
    names={m['name']:i for i,m in enumerate(items)};blocks=[]
    for model in SCIENCE['binary']:
        ns=[model['organic'],model['aggregate']]
        if all(n in names for n in ns) and stocks[ns[1]]['grain_group']!='coarse':blocks.append((model['id'],tuple(names[n] for n in ns),model['source']))
    ns=SCIENCE['ternary']['materials']
    if ns[0] in names and any(n in names for n in ns[1:]) and all(stocks[n]['grain_group']!='coarse' for n in ns if n in names and n!='Torf'):
        blocks.append((SCIENCE['ternary']['id'],tuple(names.get(n,-1) for n in ns),SCIENCE['ternary']['source']))
    return blocks

def _barycentric(point,triangle):
    x,y=point;(a,b),(c,d),(e,f)=triangle;den=(d-f)*(a-e)+(e-c)*(b-f)
    u=((d-f)*(x-e)+(e-c)*(y-f))/den;v=((f-b)*(x-e)+(a-e)*(y-f))/den;w=1-u-v
    return (max(0,u),max(0,v),max(0,w)) if min(u,v,w)>=-1e-10 else None

def _node_aux(model,index):
    waters=model.get('unavailable_water',[]);densities=model.get('bulk_density_g_ml',[])
    return (waters[index]*100 if waters else None,densities[index] if densities else None)

def _prediction(block,weights,states,height,aux=False):
    mid,indexes,source=block;local=[weights[i] if i>=0 else 0. for i in indexes];total=sum(local)
    if total<=0:return None
    binary=next((m for m in SCIENCE['binary'] if m['id']==mid),None);model=binary or SCIENCE['ternary'];nodes=node_states(mid,height)
    anchors=[];within=True
    if binary:
        x=local[1]/total;b=bracket(binary['fractions'],x)
        if b is not None:
            i,w=b;anchors=[(i,1-w),(i+1,w)]
        else:
            # A bounded convex bridge to the same stock's pure endpoint. This
            # estimates outside the measured series without extending its curve.
            within=False;w=(x-model['fractions'][-1])/(1-model['fractions'][-1]);anchors=[(len(nodes)-1,1-w),('aggregate',w)]
    else:
        x,y=local[1]/total,local[2]/total;axis=model['axis'];bx=bracket(axis,x);by=bracket(axis,y)
        if bx is not None and by is not None:
            i,u=bx;j,v=by;n=len(axis);anchors=[(i*n+j,(1-u)*(1-v)),((i+1)*n+j,u*(1-v)),(i*n+j+1,(1-u)*v),((i+1)*n+j+1,u*v)]
        else:
            within=False;a=axis[-1];h=axis[1]
            coords={6:(a,0),7:(a,h),8:(a,a),2:(0,a),5:(h,a),'peat':(1,0),'pumice':(0,1)}
            triangles=[(6,'peat',7),(7,'peat',8),('peat','pumice',8),('pumice',2,5),('pumice',5,8)]
            for tri in triangles:
                bary=_barycentric((x,y),[coords[k] for k in tri])
                if bary is not None:anchors=list(zip(tri,bary));break
            if not anchors:raise ValueError('Composition outside the mixture simplex')
    def value(key):
        if isinstance(key,int):
            out={'cc':nodes[key][0],'tp':nodes[key][1]}
            if aux:out['pwp'],out['density']=_node_aux(model,key)
            return out
        i=indexes[1] if key in ('peat','aggregate') else indexes[2]
        if i<0:raise ValueError('Missing positive pure endpoint')
        return states[i]
    anchors=[(k,w) for k,w in anchors if w>1e-12]
    cc=sum(value(k)['cc']*w for k,w in anchors);tp=sum(value(k)['tp']*w for k,w in anchors)
    out={'cc':cc,'tp':tp,'share':total,'model':mid,'source':source,'indexes':indexes,
         'within_source_domain':within,'domain_mode':'SOURCE_INTERPOLATION' if within else 'ENDPOINT_BRIDGE_ESTIMATE'}
    if aux:
        for field in ('pwp','density'):
            vals=[(value(k).get(field),w) for k,w in anchors]
            out[field]=sum(v*w for v,w in vals) if all(v is not None for v,w in vals) else sum(weights[i]*states[i][field] for i in indexes if i>=0)/total
    return out

def _ensemble(blocks,weights,states,height,aux=False):
    scenarios=[]
    for block in blocks:
        local=[weights[i] if i>=0 else 0 for i in block[1]]
        support=local[0]*sum(local[1:])
        if support<=0:continue
        pred=_prediction(block,weights,states,height,aux)
        if pred is not None:scenarios.append((support,pred))
    total=sum(x[0] for x in scenarios)
    return [(support/total,pred) for support,pred in scenarios] if total else []

def _correction(blocks,weights,states,height):
    scenarios=_ensemble(blocks,weights,states,height)
    if not scenarios:return None
    cc=tp=share=coverage=evidence=0.;mids=[];sources=[]
    for prob,pred in scenarios:
        indexes=[i for i in pred['indexes'] if i>=0];amount=pred['share']
        cc+=prob*(pred['cc']*amount/100-sum(weights[i]*states[i]['cc']/100 for i in indexes))
        tp+=prob*(pred['tp']*amount/100-sum(weights[i]*states[i]['tp']/100 for i in indexes))
        share+=prob*amount
        coverage+=prob*sum(weights[i]*states[i].get('source_coverage',0) for i in indexes)
        evidence+=prob*sum(weights[i]*states[i].get('source_evidence',0)/100 for i in indexes)
        mids.append(pred['model']);sources.append(pred['source'])
    return cc,tp,share,'+'.join(mids),'+'.join(sorted(set(sources))),coverage,evidence

def mixture_correction(items,stocks,weights,states,height):
    return _correction(eligible_blocks(items,stocks),weights,states,height)

def mixture_details(items,stocks,weights,states,height):
    scenarios=_ensemble(eligible_blocks(items,stocks),weights,states,height,True)
    pwp_delta=0.;density_adjustments=[0.]*len(items);blocks=[]
    for prob,pred in scenarios:
        indexes=[i for i in pred['indexes'] if i>=0];share=pred['share']
        pwp_delta+=prob*(pred['pwp']*share/100-sum(weights[i]*states[i]['pwp']/100 for i in indexes))
        baseline_density=sum(weights[i]*states[i]['density']/share for i in indexes)
        factor=pred['density']/baseline_density
        for i in indexes:density_adjustments[i]+=prob*states[i]['density']*(factor-1)
        blocks.append({k:pred[k] for k in ('model','source','share','domain_mode','within_source_domain')}|{'model_weight':prob,'pwp':pred['pwp'],'density':pred['density']})
    return {'blocks':blocks,'pwp_delta':pwp_delta,'density_adjustments':density_adjustments,
            'packed_density':sum(weights[i]*(states[i]['density']+density_adjustments[i])/100 for i in range(len(items))),
            'basis':'Her alt model tüm reçeteyi ayrı hesaplar; sonuçlar bileşen desteğine göre ağırlıklı ortalanır. Örtüşen malzeme payları toplanmaz. Deney dışındaki tahmin, son kaynak düğümü ile saf stok uç değeri arasında sınırlı köprüdür.'}

def compile_corrections(items,stocks,states,height,total_units,step,caps=None):
    blocks=eligible_blocks(items,stocks)
    if not blocks:return {}
    caps=caps or [total_units]*len(items);table={}
    def dist(total,limits):
        if len(limits)==1:
            if 1<=total<=limits[0]:yield (total,)
            return
        for x in range(max(1,total-sum(limits[1:])),min(limits[0],total-len(limits)+1)+1):
            for tail in dist(total-x,limits[1:]):yield (x,)+tail
    for units in dist(total_units,caps):
        value=_correction(blocks,[u*step for u in units],states,height)
        if value is not None:table[units]=value
    return table

def lookup_correction(tables,units):return tables.get(tuple(units))
