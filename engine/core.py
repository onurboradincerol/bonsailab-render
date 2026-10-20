"""BonsaiLAB V27: explicit climate bands and complete finite-grid search.

Only the Python standard library is required. Design rules are not biological
optima. Every layout-feasible 1–4 component recipe in the 5% grid is visited.
"""
from __future__ import annotations
import copy
import hashlib
import itertools
import json
import math
import time
import physics
import estimates
from pathlib import Path
from typing import Any

DB=json.loads((Path(__file__).parent/'data/database.json').read_text(encoding='utf-8'))
BY_NAME={m['name']:m for m in DB['materials']}
BY_SPECIES={s['id']:s for s in DB['species']}
BY_CLIMATE={x['id']:x for x in DB['climates']}
BY_GRAIN={x['id']:x for x in DB['grain_groups']}
RULES=DB['rules']
HARD_TO_SOURCE=set(RULES['easy_alternative']['excluded_materials'])
PRIMARY={'Pomza','Lav taşı','Akadama','Kanuma','Kiryu','Turface','Kiremit irmiği','Volkanik Tüf','Kum'}
ADDONS={'Zeolit (Klinoptilolit)','Diatomit','Vermikülit'}
ACID={'Kanuma','Torf','Sfagnum moss'}
CLASS_WEIGHT={'SAMPLE_MEASURED':1.,'TECHNICAL_DATASHEET':.85,'MEASURED_OR_MEAN':.8,'LITERATURE_SYNTHESIS':.7,'ASSUMPTION':.25,'MISSING':0.}
def identity_values(value):
    """JSON/JavaScript transport may spell 1.0 as 1; preserve numeric identity."""
    if isinstance(value,dict):return {key:identity_values(item) for key,item in value.items()}
    if isinstance(value,list):return [identity_values(item) for item in value]
    if isinstance(value,float) and value.is_integer():return int(value)
    return value

DB_HASH=hashlib.sha256(json.dumps(identity_values(DB),sort_keys=True,ensure_ascii=False).encode()).hexdigest()

class InputError(ValueError):
    pass

def clamp(value,lo,hi):
    return max(lo,min(hi,value))

def number(value,label,lo,hi):
    if isinstance(value,bool) or not isinstance(value,(int,float,str)):
        raise InputError(f'{label}: geçerli bir sayı gir.')
    try:value=float(value)
    except (ValueError,TypeError,OverflowError):raise InputError(f'{label}: geçerli bir sayı gir.')
    if not math.isfinite(value) or not lo<=value<=hi:raise InputError(f'{label}: {lo}–{hi} aralığında olmalı.')
    return value

def choice(p,key,allowed,default):
    value=p.get(key,default)
    if not isinstance(value,str) or value not in allowed:raise InputError(f'{key}: geçersiz seçim.')
    return value

def cap_for(m,sp):
    rule=RULES['shares'][m['name']]
    cap=rule.get(sp['group'],rule['default']) if isinstance(rule,dict) else rule
    if sp['group'] in ('Kozalaklı','Sukulent') and m['kind']!='Mineral granül':cap=min(cap,15)
    if sp['group']=='Sukulent' and m['name'] in ('Torf','Kokopit','Sfagnum moss','Ağaç kabuğu'):cap=min(cap,10)
    step=RULES['grid_step']
    return int(cap//step*step)

def targets(sp,p):
    if 'temp' in p or 'rh' in p:raise InputError('V27 genel iklimin yıl boyu bandını kullanır; sabit sıcaklık/nem alanlarını gönderme.')
    input_notes=[]
    if p.get('climate')=='indoor':
        p={**p,'climate':'mild',**({'location':'indoor'} if p.get('location') is None else {})};input_notes.append('Eski iç mekân iklim kaydı ılıman varsayımına taşındı; iç mekân yetiştirme yeri alanından seçilir.')
    climate=choice(p,'climate',BY_CLIMATE,'mild')
    requested_season=choice(p,'season',{'year_round','warm','shoulder','cool'},'year_round')
    season='year_round'
    if requested_season!='year_round':input_notes.append('Eski tek mevsim seçimi yıl boyu tasarıma dönüştürüldü; aynı reçetede üç mevsim bandı birlikte değerlendirilir.')
    phase=choice(p,'phase',{'pre','nebari','refine'},'nebari')
    pot=choice(p,'pot',{'air','plastic','glazed','terracotta'},'air')
    light=choice(p,'light',{'shade','filtered','full','led'},'filtered')
    wind=choice(p,'wind',{'none','low','moderate','strong'},'low')
    watering=choice(p,'watering',{'twice','daily','every2','rare'},'daily')
    location=choice(p,'location',{'outdoor','sheltered','indoor'},'outdoor')
    height=number(p.get('height',8),'Saksı yüksekliği',2,50)
    volume=number(p.get('volume',2000),'Hacim',100,100000)
    bands=DB['indoor_dry_bands'] if location=='indoor' else BY_CLIMATE[climate]['dry_bands']
    offsets={'light':{'shade':-.22,'filtered':0,'full':.3,'led':-.1}[light],
             'wind':{'none':-.1,'low':0,'moderate':.13,'strong':.3}[wind],
             'pot':{'air':.13,'plastic':0,'glazed':-.1,'terracotta':.22}[pot],
             'watering':{'twice':-.32,'daily':0,'every2':.2,'rare':.36}[watering],
             'shallow_pot':.14 if height<=5 else 0}
    offset=sum(offsets.values())
    phase_offset={'pre':-1,'nebari':0,'refine':1.3}[phase]+(1.2 if height<=6 else 0)
    scenarios=[]
    for key,label in (('warm','Sıcak / kuru dönem'),('shoulder','Geçiş dönemi'),('cool','Serin / nemli dönem')):
        low,high=[clamp(value+offset,-.65,1.4) for value in bands[key]]
        cc=[clamp(sp['target_cc']+4*d+phase_offset,16,70) for d in (low,high)]
        afp=[clamp(sp['target_afp']-2*d+(1 if pot=='air' else 0),18,50) for d in (high,low)]
        scenarios.append({'id':key,'name':label,'dry_min':low,'dry_max':high,'target_cc_min':cc[0],'target_cc_max':cc[1],'target_afp_min':afp[0],'target_afp_max':afp[1]})
    dmin=min(x['dry_min'] for x in scenarios);dmax=max(x['dry_max'] for x in scenarios)
    cc_min=min(x['target_cc_min'] for x in scenarios);cc_max=max(x['target_cc_max'] for x in scenarios)
    afp_min=min(x['target_afp_min'] for x in scenarios);afp_max=max(x['target_afp_max'] for x in scenarios)
    grain='fine' if height<=10 else 'medium' if height<=18 else 'coarse'
    grain_profile='small' if height<=6 or phase=='refine' and height<=10 else 'regular_small' if height<=12 else 'medium' if height<=18 else 'large'
    environmental=[]
    if sp['outdoor_required'] and (location=='indoor' or light=='led'):
        environmental.append('Türün dış ortam / mevsimsel ritim ihtiyacı var; iç mekân veya LED seçimi bunu doğrulamaz.')
    if sp.get('indoor_possible') and (location=='indoor' or light=='led'):environmental.append('Bu tür aydınlık, korunaklı iç ortamda yetiştirilebilir; köken, adaptasyon ve kışlama koşulları ayrıca değerlendirilir.')
    if sp['group'] in ('Tropik','Subtropik','Sukulent') and location!='indoor':
        environmental.append('Yılın serin döneminde don ve soğuk riski: türün korunacağı ortam ayrıca doğrulanmalı.')
    if climate=='continental' and location!='indoor':
        environmental.append('Karasal kışta saksıdaki köklerin donma riski ayrıca yönetilmeli.')
    return {'climate':climate,'climate_name':BY_CLIMATE[climate]['name'],'season':season,'season_scenarios':scenarios,'environment_offsets':offsets,'phase':phase,'pot':pot,'light':light,'wind':wind,'watering':watering,'location':location,'height':height,'volume':volume,'dry_min':dmin,'dry_max':dmax,'dry_pressure':(dmin+dmax)/2,'target_cc_min':cc_min,'target_cc_max':cc_max,'target_cc':(cc_min+cc_max)/2,'target_afp_min':afp_min,'target_afp_max':afp_max,'target_afp':(afp_min+afp_max)/2,'recommended_grain':grain,'grain_profile':grain_profile,'acceptable_grain_groups':[g for g,v in RULES['grain_suitability'][grain_profile].items() if v==1],'part_min':BY_GRAIN[grain]['min_mm'],'part_max':BY_GRAIN[grain]['max_mm'],'input_notes':input_notes,'environment_warnings':environmental,'climate_basis':'Yıl boyu tasarım: sıcak/kuru ucun su rezervi ve serin/nemli ucun havalanması birlikte gözetilir. Mevsim bantları ve ortam katsayıları iç model kabulleridir; ölçülmüş VPD, sulama günü veya saksı değiştirme takvimi değildir.'}

def inputs_with_inventory(p,sp):
    raw=p.get('inventory')
    if not isinstance(raw,list) or not 1<=len(raw)<=len(DB['materials']):raise InputError('Malzeme listesi 1–20 kayıt içermeli.')
    inventory={};seen=set();excluded=[];full=[]
    for row in raw:
        if not isinstance(row,dict):raise InputError('Her malzeme kaydı bir nesne olmalı.')
        name=row.get('name')
        if not isinstance(name,str) or name not in BY_NAME:raise InputError('Malzeme adı listeden seçilmeli.')
        if name in seen:raise InputError(f'{name}: stok kaydı birden fazla gönderilmiş.')
        seen.add(name)
        if not isinstance(row.get('available'),bool):raise InputError(f'{name}: Var/Yok değeri boolean olmalı.')
        m=BY_NAME[name];available=row['available']
        grain=row.get('grain_group',m['default_grain_group']) if m['grain_applicable'] else None
        legacy_bark=m['name']=='Ağaç kabuğu' and grain is None and row.get('min_mm') is None and row.get('max_mm') is None
        if legacy_bark:grain=m['default_grain_group']
        if m['grain_applicable']:
            if not isinstance(grain,str) or grain not in BY_GRAIN:raise InputError(f'{name}: üç dane grubundan birini seç.')
            if not legacy_bark and ('min_mm' in row or 'max_mm' in row) and (row.get('min_mm')!=BY_GRAIN[grain]['min_mm'] or row.get('max_mm')!=BY_GRAIN[grain]['max_mm']):raise InputError(f'{name}: dane boyutu seçilen hazır grupla eşleşmiyor.')
        entry={'name':name,'available':available,'grain_group':grain,'min_mm':BY_GRAIN[grain]['min_mm'] if grain in BY_GRAIN else None,'max_mm':BY_GRAIN[grain]['max_mm'] if grain in BY_GRAIN else None}
        full.append(entry)
        if available:
            if cap_for(m,sp)==0:excluded.append(f'{name}: V26 tasarım kuralında otomatik reçeteye alınmıyor.')
            else:inventory[name]=entry
    if not inventory:raise InputError('En az bir seçime uygun malzemeyi Var olarak işaretle.')
    return inventory,full,excluded

def overlap_fit(a,b,c,d):
    overlap=max(0,min(b,d)-max(a,c));union=max(b,d)-min(a,c)
    return overlap/union if union>0 else 0.

def grain_fit(m,stock,t):
    if not m['grain_applicable']:return None
    return RULES['grain_suitability'][t['grain_profile']][stock['grain_group']]

def prepare_material(m,stock):
    material=copy.deepcopy(m);profiles=m['reference_profiles']
    if profiles and stock['grain_group']:
        a,b=stock['min_mm'],stock['max_mm']
        profile=max(profiles,key=lambda x:(overlap_fit(a,b,x['min_mm'],x['max_mm']),-abs((a+b)-(x['min_mm']+x['max_mm']))))
        material.update({k:profile[k] for k in ('cc','afp','tp','awc','density')})
        material['reference_used']=profile;material['source_size_fit']=overlap_fit(a,b,profile['min_mm'],profile['max_mm'])
        if m['name']=='Pomza' and len(profiles)>1:
            ordered=sorted(profiles,key=lambda x:math.sqrt(x['min_mm']*x['max_mm']))
            axis=[math.log(math.sqrt(x['min_mm']*x['max_mm'])) for x in ordered]
            bracket=physics.bracket(axis,math.log(math.sqrt(a*b)))
            if bracket is not None:
                i,w=bracket;left,right=ordered[i:i+2]
                for key in ('cc','afp','tp','awc','density'):material[key]=left[key]*(1-w)+right[key]*w
                profile={**profile,'id':'PUMICE_INTERPOLATED','min_mm':a,'max_mm':b,'interpolated':True,
                         'reference_height_cm':left['reference_height_cm'],'source':left['source'],
                         **{key:material[key] for key in ('cc','afp','tp','awc','density')},'endpoints':[{'id':left['id'],'weight':1-w,'min_mm':left['min_mm'],'max_mm':left['max_mm']},
                                      {'id':right['id'],'weight':w,'min_mm':right['min_mm'],'max_mm':right['max_mm']}],
                         'note':'Logaritmik geometrik ortalama dane çapında sınırlı interpolasyon; bu stok fraksiyonu ölçülmedi.'}
                material['reference_used']=profile
                material['source_size_fit']=sum(overlap_fit(a,b,x['min_mm'],x['max_mm'])*z for x,z in ((left,1-w),(right,w)))
    else:material['reference_used']=None;material['source_size_fit']=None
    return estimates.complete_material(material,DB["numeric_estimation"])

def measure_quality(m,k):return CLASS_WEIGHT.get(m['provenance'][k]['class'],0)

def hard_to_source(m):return m['name'] in HARD_TO_SOURCE

def easy_stock(m,inv):return m['name'] not in HARD_TO_SOURCE

def base_material_preference(m,sp,t):
    n=m['name'];g=sp['group']
    pref={'Pomza':0,'Lav taşı':.24,'Akadama':.17,'Kanuma':1.6,'Kiryu':.33,'Perlit':.25,'Kiremit irmiği':.8,'Turface':.5,'Volkanik Tüf':.92,'Kum':1.15,'Torf':.5,'Kokopit':.48,'Ağaç kabuğu':.52,'Sfagnum moss':.65,'Vermikülit':1.6,'Humus':2,'Diatomit':2.5,'Zeolit (Klinoptilolit)':2.5,'Saksı toprağı':1.35}.get(n,2)
    if g=='Asidik':pref+= {'Kanuma':-2.5,'Torf':-.95,'Sfagnum moss':-.85,'Lav taşı':.5,'Kiremit irmiği':.6}.get(n,0)
    elif n=='Kanuma':pref+=.9
    if g=='Kozalaklı':pref+= {'Kiryu':-.5,'Lav taşı':-.2,'Kokopit':.5}.get(n,0)
    if g=='Sukulent':pref+= {'Lav taşı':-.4,'Pomza':-.15,'Torf':1,'Kokopit':1,'Vermikülit':1.2}.get(n,0)
    if g=='Tropik':pref+= {'Kokopit':-.32,'Akadama':-.1}.get(n,0)
    if g=='Akdeniz':pref+= {'Lav taşı':-.18,'Ağaç kabuğu':.15}.get(n,0)
    if t['dry_pressure']>.5:pref+= {'Kokopit':-.35,'Torf':-.18,'Lav taşı':.18}.get(n,0)
    if t['dry_pressure']<-.2:pref+= {'Lav taşı':-.1,'Kokopit':.25}.get(n,0)
    return pref

def layout_valid(items,shares,sp,inv=None):
    g=sp['group'];primary=sum(w for m,w in zip(items,shares) if m['name'] in PRIMARY)
    organic=sum(w for m,w in zip(items,shares) if m['kind']!='Mineral granül')
    addon=sum(w for m,w in zip(items,shares) if m['name'] in ADDONS)
    acid=sum(w for m,w in zip(items,shares) if m['name'] in ACID)
    return sum(shares)==100 and all(0<w<=cap_for(m,sp) for m,w in zip(items,shares)) and primary>=RULES['primary_min'].get(g,RULES['primary_min']['default']) and organic<=RULES['organic_max'].get(g,RULES['organic_max']['default']) and addon<=RULES['addon_max'] and (g!='Asidik' or acid>=RULES['acid_min'])

def component_state(m,height):
    state=physics.material_state(m,height)
    quality=min(measure_quality(m,k) for k in ('cc','afp','tp'))
    if state.get('density') is None:state['density']=m['density']
    if state.get('pwp') is None:
        if state['curve'] and state['curve']['kind']=='fitted_exponential':state['pwp']=state['curve']['pwp']
        else:
            ref=m['tp']*m['cc']/max(1e-12,m['cc']+m['afp']);state['pwp']=state['reference_cc']*(1-clamp(m['awc']/max(1e-12,ref),0,1))
    state['source_coverage']=int(quality>=.7)
    state['source_evidence']=quality*(m['source_size_fit'] or 0)
    return state

def physical_estimate(items,shares,sp,t,inv):
    prepared=[prepare_material(m,inv[m['name']]) for m in items]
    states=[component_state(m,t['height']) for m in prepared]
    tp=sum(x['tp']*w/100 for x,w in zip(states,shares))
    cc=sum(x['cc']*w/100 for x,w in zip(states,shares))
    cc_ref=sum(x['reference_cc']*w/100 for x,w in zip(states,shares))
    coupling=physics.mixture_correction(items,inv,shares,states,t['height'])
    reference_states=[component_state(m,physics.SCIENCE['reference_height_cm']) for m in prepared]
    ref_coupling=physics.mixture_correction(items,inv,shares,reference_states,physics.SCIENCE['reference_height_cm'])
    if ref_coupling:cc_ref+=ref_coupling[0]
    baseline_cc,baseline_tp=cc,tp
    if coupling:cc+=coupling[0];tp+=coupling[1]
    cc=clamp(cc,0,tp)
    sized=sum(w for m,w in zip(items,shares) if m['grain_applicable'])
    fit=sum((grain_fit(m,inv[m['name']],t) or 0)*w for m,w in zip(items,shares))/sized if sized else None
    evidence=sum(w*x['source_evidence']/100 for x,w in zip(states,shares))-(coupling[6] if coupling else 0)
    sourced=sum(w*x['source_coverage'] for x,w in zip(states,shares))-(coupling[5] if coupling else 0)
    source_size_known=sum(w for m,w in zip(prepared,shares) if m['source_size_fit'] is not None)
    chemistry=estimates.chemical_estimate(prepared,shares,DB['numeric_estimation'])
    chemistry.update(species_band=[sp['ph_min'],sp['ph_max']],point_in_species_band=sp['ph_min']-1e-9<=chemistry['mixture_ph']<=sp['ph_max']+1e-9,range_overlaps_species_band=chemistry['range_max']>=sp['ph_min'] and chemistry['range_min']<=sp['ph_max'])
    details=physics.mixture_details(items,inv,shares,states,t['height'])
    extra=estimates.additional_estimates(prepared,shares,states,cc,DB['numeric_estimation'],t['volume'],details)
    awc_cov=sum(w for m,w in zip(prepared,shares) if m['awc'] is not None and measure_quality(m,'awc')>=.7)
    contributions=[{'name':m['name'],'share':w,'cc_points':x['cc']*w/100,'afp_points':(x['tp']-x['cc'])*w/100,
                    'tp_points':x['tp']*w/100,'component_cc':x['cc'],'component_tp':x['tp'],
                    'basis':x['basis'],'source':x['source']} for m,w,x in zip(prepared,shares,states)]
    interaction={'applied':bool(coupling),'model':coupling[3] if coupling else None,'source':coupling[4] if coupling else None,
                 'share':coupling[2] if coupling else 0,'cc_points':coupling[0] if coupling else 0,
                 'tp_points':coupling[1] if coupling else 0,'afp_points':coupling[1]-coupling[0] if coupling else 0,
                 'basis':'Kaynak aralığında interpolasyon, dışında etiketli saf uç nokta köprüsü; her tam reçete senaryosu ağırlıklı ortalanır. Fark numune/ölçüm ve karışım etkisini içerir; saf paketlenme katsayısı değildir.' if coupling else 'Geçerli deney aralığında eşleşen alt karışım yok; bileşen eğrileri lineer birleştirildi.',
                 'scope':physics.SCIENCE['scope_note'],'blocks':details['blocks'],'ensemble_basis':details['basis']}
    return {**extra,'cc':cc,'afp':tp-cc,'tp':tp,'cc_reference':cc_ref,'height_delta':cc-cc_ref,
            'height_model':'Su tutma eğrisinin 0–H cm boyunca ortalaması; sabit kesit ve serbest drenaj kabulü. Mineral eğri şekli referans CC ile kalibre edilmiş varsayımdır.',
            'ph_index':sum(m['ph']*w/100 for m,w in zip(prepared,shares)),
            'chemistry':chemistry,'cec':extra['cec'],'cec_basis':extra['cec_basis'],'physical_coverage':sourced,'size_coverage':fit,'source_size_known_share':source_size_known,
            'evidence_index':max(0,evidence),'model_confidence':'Kaynak eğrilerinden ölçülmemiş stok karışımına aktarım',
            'awc_coverage':awc_cov,'awc_partial':sum(m['awc']*w/100 for m,w in zip(prepared,shares) if m['awc'] is not None and measure_quality(m,'awc')>=.7),
            'awc_basis':extra['awc_basis'],
            'contributions':contributions,'interaction':interaction,'linear_cc':baseline_cc,'linear_tp':baseline_tp,
            'reference_profiles':[{'name':m['name'],'reference':m['reference_used'],'source_size_fit':m['source_size_fit']} for m in prepared],
            'raw_phase_gap':sum((m['cc']+m['afp']-m['tp'])*w/100 for m,w in zip(prepared,shares))}

def viability(items,shares,sp,t,inv,est):
    reasons=[];a=RULES['acceptance']
    if not layout_valid(items,shares,sp,inv):reasons.append('İskelet, organik pay veya asidik bileşen sınırı sağlanmıyor.')
    if est['afp']<max(a['min_afp_floor'],t['target_afp_max']-a['max_afp_deficit'])-1e-9:reasons.append('İklim bandında öngörülen havalanma asgari eşiğin altında.')
    if est['cc']<max(a['min_cc_floor'],t['target_cc_max']-a['max_cc_deficit'])-1e-9:reasons.append('İklim bandında öngörülen su rezervi asgari eşiğin altında.')
    if est.get('size_coverage') is not None and est['size_coverage']<a['min_grain_overlap']-1e-9:reasons.append('Dane grubu hedefle çok az örtüşüyor; asgari tasarım uyumu sağlanmıyor.')
    return reasons

def _soft_risk(sp,t,cc,afp,fit,evidence,coverage,ph):
    a=RULES['acceptance']
    return bool(sp['group']=='Asidik' or t['environment_warnings'] or fit is None or fit<a['conditional_grain_overlap']-1e-9 or evidence<a['conditional_source_index']-1e-9 or coverage<a['conditional_physical_share'] or cc<t['target_cc_max']-a['conditional_target_deficit']-1e-9 or afp<t['target_afp_max']-a['conditional_target_deficit']-1e-9)

def environment_score(sp,t,cc,afp,ph):
    s=RULES['score']
    score=2*(max(0,t['target_cc_max']-cc-2)/9)**2+s['cc_excess_weight']*(max(0,cc-t['target_cc_max']-s['cc_excess_tolerance'])/9)**2
    score+=2.6*(max(0,t['target_afp_max']-afp-2)/9)**2+s['afp_excess_weight']*(max(0,afp-t['target_afp_max']-s['afp_excess_tolerance'])/9)**2
    return score  # Buffered-solid mixture pH is not inferred from component averages.

def reference_mix(sp,inv,mode='technical'):
    raw={n:w for n,w in RULES['reference_mix'].get(sp['group'],{}).items() if n in inv and (mode!='economical' or easy_stock(BY_NAME[n],inv))}
    total=sum(raw.values())
    return {n:w/total for n,w in raw.items()} if total else {}

def evaluate(items,shares,sp,t,inv,mode='technical'):
    e=physical_estimate(items,shares,sp,t,inv)
    score=environment_score(sp,t,e['cc'],e['afp'],e['ph_index'])
    for m,w in zip(items,shares):
        prepared=prepare_material(m,inv[m['name']]);fit=grain_fit(m,inv[m['name']],t)
        source_fit=prepared['source_size_fit'] or 0
        score+=w/100*(.65*base_material_preference(m,sp,t)+.85*(1-min(measure_quality(m,k) for k in ('cc','afp','tp')))+.35*(1-source_fit)+(1.1*(1-fit) if fit is not None else 0))
    score+=.09*max(0,len(items)-2)+(.85 if any(m['name'] in ADDONS-{'Vermikülit'} for m in items) else 0)
    if mode=='technical':score+=.4*sum(w for m,w in zip(items,shares) if hard_to_source(m))/100
    ref=reference_mix(sp,inv,mode)
    if ref:score+=RULES['score']['reference_weight']*(sum((w/100)**2 for w in shares)+sum(v*v for v in ref.values())-2*sum(w/100*ref.get(m['name'],0) for m,w in zip(items,shares)))
    return score,e

def candidate_rank(items,shares,sp,t,inv,score,est,mode):
    reasons=viability(items,shares,sp,t,inv,est)
    tier=2 if reasons else 1 if _soft_risk(sp,t,est['cc'],est['afp'],est['size_coverage'],est['evidence_index'],est['physical_coverage'],est['ph_index']) else 0
    return selection_rank(tier,len(reasons),est['chemistry']['mixture_ph'],sp,score,items,shares)

def selection_rank(tier,failures,ph,sp,score,items,shares):
    # Physical hard floors first, then estimated pH feasibility/nearest distance;
    # source confidence and physical preference score decide among feasible ties.
    distance=max(0.,sp['ph_min']-ph,ph-sp['ph_max'])
    if distance<=1e-9:distance=0.
    return (int(failures>0),failures,int(distance>0),round(distance,9),tier,round(score,9),len(items),tuple((m['name'],w) for m,w in zip(items,shares)))


def distributions(total,caps):
    if len(caps)==1:
        if 1<=total<=caps[0]:yield (total,)
        return
    for value in range(max(1,total-sum(caps[1:])),min(caps[0],total-len(caps)+1)+1):
        for tail in distributions(total-value,caps[1:]):yield (value,)+tail

def search_variants(mats,sp,t,inv,modes):
    """Complete search; evaluate the linear data in a tight loop, finalize winners."""
    if any(mode not in ('technical','economical') for mode in modes):raise InputError('Geçersiz tasarım modu.')
    step=RULES['grid_step'];total_units=100//step;max_components=RULES['max_components']
    start=time.perf_counter();best={mode:None for mode in modes};count=0;ph_counts={mode:0 for mode in modes};physical_counts={mode:0 for mode in modes}
    mats=sorted(mats,key=lambda m:m['name']);vectors=[];states=[];references={mode:reference_mix(sp,inv,mode) for mode in modes};ref_norms={mode:sum(v*v for v in ref.values()) for mode,ref in references.items()}
    for m in mats:
        x=prepare_material(m,inv[m['name']]);fit=grain_fit(m,inv[m['name']],t);source_fit=x['source_size_fit'] or 0;quality=min(measure_quality(m,k) for k in ('cc','afp','tp'))
        state=component_state(x,t['height']);states.append(state)
        vectors.append((state['cc'],state['tp'],x['ph'],(fit or 0) if fit is not None else 0,quality*source_fit,1 if quality>=.7 else 0,1 if m['name'] in PRIMARY else 0,1 if m['kind']!='Mineral granül' else 0,1 if m['name'] in ADDONS else 0,1 if m['name'] in ACID else 0,1 if hard_to_source(m) else 0,.65*base_material_preference(m,sp,t)+.85*(1-quality)+.35*(1-source_fit)+(1.1*(1-fit) if fit is not None else 0),{mode:ref.get(m['name'],0) for mode,ref in references.items()},1 if m['grain_applicable'] else 0,x['numeric_estimation']['relative_buffer']))
    primary_min=RULES['primary_min'].get(sp['group'],RULES['primary_min']['default'])/step
    organic_max=RULES['organic_max'].get(sp['group'],RULES['organic_max']['default'])/step
    a=RULES['acceptance'];acid=sp['group']=='Asidik';cc_floor=max(a['min_cc_floor'],t['target_cc_max']-a['max_cc_deficit']);afp_floor=max(a['min_afp_floor'],t['target_afp_max']-a['max_afp_deficit'])
    for k in range(1,min(max_components,len(mats))+1):
        for indexes in itertools.combinations(range(len(mats)),k):
            items=tuple(mats[i] for i in indexes);vs=tuple(vectors[i] for i in indexes);caps=tuple(cap_for(m,sp)//step for m in items)
            if sum(caps)<total_units:continue
            if sum(cap*v[6] for cap,v in zip(caps,vs))<primary_min:continue
            if acid and sum(cap*v[9] for cap,v in zip(caps,vs))<RULES['acid_min']/step:continue
            difficult_present=any(not easy_stock(m,inv) for m in items);extra=.09*max(0,k-2)+(.85 if any(m['name'] in ADDONS-{'Vermikülit'} for m in items) else 0)
            tables=physics.compile_corrections(items,inv,[states[i] for i in indexes],t['height'],total_units,step,caps)
            for units in distributions(total_units,caps):
                primary=sum(u*v[6] for u,v in zip(units,vs));organic=sum(u*v[7] for u,v in zip(units,vs));addon=sum(u*v[8] for u,v in zip(units,vs))
                if primary<primary_min or organic>organic_max or addon>RULES['addon_max']/step or acid and sum(u*v[9] for u,v in zip(units,vs))<RULES['acid_min']/step:continue
                count+=1
                cc=sum(u*v[0] for u,v in zip(units,vs))/total_units;tp=sum(u*v[1] for u,v in zip(units,vs))/total_units
                coupling=physics.lookup_correction(tables,units) if tables else None
                if coupling:cc+=coupling[0];tp+=coupling[1]
                cc=clamp(cc,0,tp);afp=tp-cc
                ph=sum(u*v[2]*v[14] for u,v in zip(units,vs))/sum(u*v[14] for u,v in zip(units,vs))
                sized=sum(u*v[13] for u,v in zip(units,vs));fit=sum(u*v[3] for u,v in zip(units,vs))/sized if sized else None
                evidence=sum(u*v[4] for u,v in zip(units,vs))/total_units;coverage=sum(u*v[5] for u,v in zip(units,vs))*step
                if coupling:evidence-=coupling[6];coverage-=coupling[5]
                failures=int(cc<cc_floor-1e-9)+int(afp<afp_floor-1e-9)+int(fit is not None and fit<a['min_grain_overlap']-1e-9)
                tier=2 if failures else 1 if _soft_risk(sp,t,cc,afp,fit,evidence,coverage,ph) else 0
                score=environment_score(sp,t,cc,afp,ph)
                score+=sum(u*v[11] for u,v in zip(units,vs))/total_units+extra
                difficult=sum(u*v[10] for u,v in zip(units,vs))/total_units
                for mode in modes:
                    if mode=='economical' and difficult_present:continue
                    sc=score+.4*difficult if mode=='technical' else score
                    if references[mode]:sc+=RULES['score']['reference_weight']*(sum(u*u for u in units)/(total_units**2)+ref_norms[mode]-2*sum(u*v[12][mode] for u,v in zip(units,vs))/total_units)
                    if not failures:
                        physical_counts[mode]+=1
                        if sp['ph_min']-1e-9<=ph<=sp['ph_max']+1e-9:ph_counts[mode]+=1
                    rank=selection_rank(tier,failures,ph,sp,sc,items,tuple(u*step for u in units))
                    if best[mode] is None or rank<best[mode][0]:best[mode]=(rank,items,tuple(u*step for u in units))
    results={}
    for mode,winner in best.items():
        if winner is None:results[mode]=None;continue
        rank,items,shares=winner;score,est=evaluate(items,shares,sp,t,inv,mode)
        # Guard equivalence between the accelerated search and public evaluation.
        assert abs(rank[5]-score)<1e-7,(rank[5],score)
        assert rank==candidate_rank(items,shares,sp,t,inv,score,est,mode)
        results[mode]=(rank,score,items,shares,est,viability(items,shares,sp,t,inv,est))
    return results,{'complete':True,'ph_selection':{mode:{'physical_feasible_candidates':physical_counts[mode],'ph_feasible_candidates':ph_counts[mode],'ph_band':[sp['ph_min'],sp['ph_max']],'basis':'Fiziksel asgari koşulları sağlayan adaylar arasında önce tahmini pH bandı; yoksa banda en yakın tahmin.'} for mode in modes},'candidate_count':count,'max_components':max_components,'step_percent':step,'material_count':len(mats),'seconds':round(time.perf_counter()-start,4),'scope':f'Yalnız seçili stok, 1–{max_components} bileşen ve %{step} adım; bu sonlu alanda tam tarama.'}

def optimize(mats,sp,t,inv,mode):return search_variants(mats,sp,t,inv,[mode])[0][mode]

def recipe_grain_recommendation(items,shares,sp,t,inv,mode):
    sized=[m for m in items if m['grain_applicable']]
    if not sized:return None
    candidates=[]
    for gid in t['acceptable_grain_groups']:
        group=BY_GRAIN[gid];scenario={n:dict(row) for n,row in inv.items()}
        for m in sized:scenario[m['name']].update(grain_group=gid,min_mm=group['min_mm'],max_mm=group['max_mm'])
        score,estimate=evaluate(items,shares,sp,t,scenario,mode)
        rank=candidate_rank(items,shares,sp,t,scenario,score,estimate,mode)
        changed_share=sum(w for m,w in zip(items,shares) if m['grain_applicable'] and inv[m['name']]['grain_group']!=gid)
        candidates.append((rank[:6]+(changed_share,gid),gid,estimate))
    selected_rank,gid,hypothetical=min(candidates,key=lambda x:x[0]);group=BY_GRAIN[gid]
    scenario_tier=selected_rank[4]
    scenario={n:dict(row) for n,row in inv.items()}
    for m in sized:scenario[m['name']].update(grain_group=gid,min_mm=group['min_mm'],max_mm=group['max_mm'])
    scenario_reasons=viability(items,shares,sp,t,scenario,hypothetical)
    if not hypothetical['chemistry']['point_in_species_band']:scenario_reasons.append('Önerilen dane senaryosunda tahmini pH türün tercih bandı dışında; kimyasal uyum kontrolü gerekli.')
    rows=[{'name':m['name'],'stock_group':inv[m['name']]['grain_group'],'recommended_group':gid if m['grain_applicable'] else None,
           'stock_matches':inv[m['name']]['grain_group']==gid if m['grain_applicable'] else None,
           'stock_acceptable':grain_fit(m,inv[m['name']],t)>=.95 if m['grain_applicable'] else None} for m in items]
    changed=any(row['stock_matches'] is False for row in rows)
    return {'group':gid,'label':group['name'],'min_mm':group['min_mm'],'max_mm':group['max_mm'],'components':rows,
            'requires_different_stock':changed,'basis':'Bu reçetenin oranları sabit tutularak saksı/aşamaya uygun dane grupları karşılaştırıldı. İç model önerisi; ölçülmüş optimum değil.',
            'scenario_status':('inadequate' if scenario_tier==2 else 'conditional' if scenario_tier==1 or not hypothetical['chemistry']['point_in_species_band'] else 'ok'),'scenario_reasons':scenario_reasons,
            'stock_calculation_unchanged':True,'note':'Kartın su/hava hesabı mevcut stokla yapıldı. Önerilen dane farklıysa yeni fraksiyonla tekrar hesapla. Eleme daha büyük taneler oluşturmaz.' if changed else 'Mevcut stok bu reçetenin önerilen dane grubuyla eşleşiyor. Toz ve elek altını ayır; gerçek dağılımı doğrula.',
            'caution':'Dane değişikliği tek başına bu reçetenin tasarım eşiklerini sağlamıyor.' if scenario_reasons else None,
            'candidate_groups':t['acceptable_grain_groups'],'scenario_values':{'cc':hypothetical['cc'],'afp':hypothetical['afp'],'ph_index':hypothetical['ph_index'],'mixture_ph':hypothetical['chemistry']['mixture_ph'],'species_band':hypothetical['chemistry']['species_band']}}

def variant(result,sp,t,inv,mode):
    if result is None:return {'status':'unavailable','mode':mode,'selected':[],'estimate':None,'warnings':['Akadama, Kanuma, Kiryu ve Turface dışındaki seçili stokta, bu arama alanının düzen şartlarını sağlayan aday yok.' if mode=='economical' else 'Seçili stokta, 1–4 bileşen ve %5 adım altında düzen kısıtlarını sağlayan aday yok.'],'reasons':[],'difficult_share':0,'grain_recommendation':None,'acceptance_label':'Bu arama alanında aday yok'}
    rank,score,items,shares,e,reasons=result;warnings=list(reasons)+t['environment_warnings'];rows=[]
    for m,w in zip(items,shares):
        stock=inv[m['name']];x=prepare_material(m,stock);fit=grain_fit(m,stock,t)
        rows.append({'name':m['name'],'share':w,'amount_ml':round(w*t['volume']/100,4),'role':m['role'],'grade':'Alan bazlı','grain_group':stock['grain_group'],'size_min':stock['min_mm'],'size_max':stock['max_mm'],'size_compat':round(fit*100,1) if fit is not None else None,'source_size_compat':round(x['source_size_fit']*100,1) if x['source_size_fit'] is not None else None,'reference_profile':x['reference_used'],'difficult_to_source':hard_to_source(m),'numeric_properties':{key:x[key] for key in ('ph','cec','density','awc','cc','afp','tp')},'numeric_estimation':x['numeric_estimation'],'property_provenance':x['provenance'],'sources':sorted({s for p in x['provenance'].values() for s in p['sources']})})
        if x['source_size_fit'] is None:warnings.append(f'{m["name"]}: fiziksel kaynak numunesiyle ürün/fraksiyon eşleşmesi bilinmiyor.')
        elif x['source_size_fit']<.75:warnings.append(f'{m["name"]}: stok grubu ile kullanılan kaynak numunesi farklı; aktarılabilirlik sınırlı.')
    if e['size_coverage'] is not None and e['size_coverage']<.45:warnings.append('Dane grubu hedef tasarım bandıyla az örtüşüyor; bu reçete koşul kontrolü gerektirir.')
    if e['physical_coverage']<70:warnings.append('Fiziksel özelliklerin önemli bölümü varsayımsal; kaynaklı pay laboratuvar karışım doğrulaması değildir.')
    if e['cc']<t['target_cc_max']-2:warnings.append('İklim bandının kurutucu ucunda CC tasarım hedefi tam sağlanmıyor.')
    if e['afp']<t['target_afp_max']-2:warnings.append('İklim bandının nemli ucunda AFP tasarım hedefi tam sağlanmıyor.')
    if e['awc_coverage']<100:warnings.append('Toplam kullanılabilir suyun eksik bileşenleri malzeme ailesi önkabulleriyle tahmin edildi.')
    if any(not m['cec_density_compatible'] or m['density'] is None for m in items):warnings.append('CEC ve yoğunlukta eksik veya farklı fraksiyonlu veriler tahmini aktarım ile tamamlandı.')
    if sp['group']=='Asidik':warnings.append('Asitlik doğrulanmadı: gerçek karışım pH ölçümü ve sulama suyu alkalinitesi kontrolü gerekir.')
    else:warnings.append('pH göreli tamponlama önkabulleriyle tahmin edildi; ürün ve sulama suyu etkisi yaklaşık aralığın dışına taşıyabilir.')
    if e['interaction']['applied']:warnings.append('Kaynak aralığında interpolasyon, dışında etiketli uç nokta köprüsü kullanıldı; malzeme ailesine aktarım gerçek stok doğrulaması değildir.')
    if t['dry_max']>.8:warnings.append('Sıcak/kuru dönem uçlarında sulama erişimi, saksı hacmi ve gölgeleme ayrıca yönetilmeli.')
    tier=2 if reasons else 1 if _soft_risk(sp,t,e['cc'],e['afp'],e['size_coverage'],e['evidence_index'],e['physical_coverage'],e['ph_index']) else 0;physical_status='inadequate' if tier==2 else 'conditional' if tier==1 else 'ok'
    status='conditional' if physical_status=='ok' and not e['chemistry']['point_in_species_band'] else physical_status
    if not e['chemistry']['point_in_species_band']:warnings.insert(0,f"Tahmini pH {e['chemistry']['mixture_ph']:.1f}, türün {sp['ph_min']}–{sp['ph_max']} tercih bandının dışında; kimyasal uyum kontrolü gerekli.")
    if not e['chemistry']['range_overlaps_species_band']:warnings.insert(0,'pH duyarlılık aralığı da türün tercih bandıyla kesişmiyor; kimyasal uyumsuzluk riski yüksek.')
    return {'status':status,'physical_status':physical_status,'mode':mode,'score':score,'estimate':e,'selected':sorted(rows,key=lambda x:(-x['share'],x['name'])),'warnings':list(dict.fromkeys(warnings)),'reasons':reasons,'difficult_share':sum(w for m,w in zip(items,shares) if hard_to_source(m)),'grain_recommendation':recipe_grain_recommendation(items,shares,sp,t,inv,mode),'acceptance_label':{'ok':'Model kısıtları sağlandı','conditional':'Koşullu tasarım / kontrol gerekli','inadequate':'Tasarım eşikleri sağlanmadı'}[status]}

def calculate(payload:dict[str,Any]):
    if not isinstance(payload,dict):raise InputError('İstek bir nesne olmalı.')
    sid=payload.get('species_id')
    if not isinstance(sid,str) or sid not in BY_SPECIES:raise InputError('Listeden geçerli bir tür seç.')
    sp=BY_SPECIES[sid];t=targets(sp,payload);inv,full,excluded=inputs_with_inventory(payload,sp)
    modes=['technical','economical']
    solutions,search=search_variants([BY_NAME[n] for n in inv],sp,t,inv,modes)
    tech=variant(solutions['technical'],sp,t,inv,'technical');econ=variant(solutions['economical'],sp,t,inv,'economical')
    for mode,v in (('technical',tech),('economical',econ)):
        v['ph_selection']=search['ph_selection'][mode]
        if v['estimate']:
            e=v['estimate'];tolerance=RULES['acceptance']['conditional_target_deficit']
            v['season_checks']=[{**x,'cc_scenario':e['cc'],'afp_scenario':e['afp'],'cc_target_met':e['cc']>=x['target_cc_max']-tolerance-1e-9,'afp_target_met':e['afp']>=x['target_afp_max']-tolerance-1e-9,'target_tolerance':tolerance} for x in t['season_scenarios']]

        if v['estimate'] and (not v['estimate']['chemistry']['point_in_species_band'] or not search['ph_selection'][mode]['physical_feasible_candidates']):
            selection=search['ph_selection'][mode]
            message=('Fiziksel asgari koşulları sağlayan reçete yok. Önce ihlal sayısı en az olan adaylar, sonra bu grup içinde pH bandına yakınlık karşılaştırıldı.' if not selection['physical_feasible_candidates'] else 'Seçili stok ve oran sınırlarında fiziksel asgari koşullarla birlikte pH tercih bandına giren reçete bulunamadı; fiziksel koşulları sağlayanlar arasında banda en yakın tahmin seçildi.')
            v['warnings'].insert(0,message)

    notes=excluded+t['input_notes']+['Tek reçete üç mevsim bandıyla değerlendirilir; karışım yalnız saksı değişiminin yapıldığı mevsime göre seçilmez. Güncel sulama ve koruma mevsim boyunca yönetilir.','Kolay temin alternatifi Akadama, Kanuma, Kiryu ve Turface dışındaki Var işaretli malzemelerle aranır.']
    if any(n in inv for n in ('Torf','Kokopit','Ağaç kabuğu')):notes.append('Organik malzemelerde pH referans varsayımıdır; fiziksel eğriler literatürden malzeme ailesine aktarılır; ürünler arasında değişebilir. Kabuk dane seçimi uygunluk önerisine katılır. Boyuta özgü saf malzeme eğrisi yoktur; iri grupta deney karışımı aktarımı kapalıdır.')
    if all(v['status']=='unavailable' for v in (tech,econ)):
        notes.append('Sınırlar ve katkı/iskelet şartları mevcut stokta birlikte sağlanamıyor. Limit tablosunu incele; arama alanı %5 adım ve en fazla dört bileşenle sınırlı.')
    normalized={k:t[k] for k in ('climate','season','phase','pot','light','wind','watering','location','height','volume')}
    normalized.update({'species_id':sid,'inventory':full})
    fingerprint=hashlib.sha256(json.dumps(identity_values(normalized),sort_keys=True,ensure_ascii=False).encode()).hexdigest()
    return {'application':'BonsaiLAB V27','species':sp,'inputs':t,'request':normalized,'request_sha256':fingerprint,'request_identity_version':2,'database_sha256':DB_HASH,'technical':tech,'economical':econ,'notes':notes,'limits':{n:cap_for(BY_NAME[n],sp) for n in inv},'rule_source':'V26_RULES','search':search,'provenance_note':'Model kısıtları biyolojik güvenlik onayı değildir. Tüm fiziksel ve kimyasal sonuçlara sayısal tahmin verilir; eksikler açık önkabullerle tamamlanır. Aralıklar tasarım duyarlılığıdır, güven aralığı değildir.', 'science_version':physics.SCIENCE['version']}
