"""장바구니 역설계 | Python 3.10+
GitHub에 app.py와 requirements.txt 업로드 → Streamlit Community Cloud에서 app.py 배포.
외부 API, 로그인, DB 불필요. 입력은 현재 세션에만 유지됩니다.
재료량·가격은 계산용 예시이며 실제 영양·시세·소비기한 정보가 아닙니다.
QR 공유는 배포 주소를 브라우저에서 QR로 공유하세요. 공용 상태 동기화는 지원하지 않습니다.
"""
import requests
import json
import re
from bs4 import BeautifulSoup
import itertools
import hashlib
import math
import streamlit as st

# 재료: 구매 단위 수량, 단위, 포장 가격. 달걀은 개, 나머지는 g.
ING={
 '쌀':(1000,'g',4500),'달걀':(10,'개',4500),'두부':(300,'g',1800),
 '돼지고기':(500,'g',8000),'닭고기':(500,'g',6500),'양배추':(1000,'g',3500),
 '양파':(1000,'g',2800),'대파':(300,'g',2000),'감자':(1000,'g',4000),
 '당근':(500,'g',2000),'애호박':(300,'g',1800),'김치':(500,'g',5000),
 '참치':(150,'g',2200),'우동면':(400,'g',2400),'어묵':(300,'g',2400),
}
PRICE_INFO = [('쌀', 20000, 65200, '믿고먹는우리쌀 20kg', 'disp/theme/category.ssg?dispCtgId=6000223978'), ('달걀', 10, 5380, '동물복지 유정란 L 10구', 'disp/category.ssg?dispCtgId=6000228040'), ('두부', 300, 1680, '행복한콩 부침두부 300g', 'search.ssg?query=들깨순두부'), ('돼지고기', 500, 9900, '도드람 냉장 미박 앞다리 구이용 500g', 'search.ssg?query=미박앞다리살'), ('닭고기', 500, 11880, '하림 냉장 닭다리살 정육 500g · 정상가', 'disp/category.ssg?dispCtgId=6000215203'), ('양배추', 800, 3480, '한끼 양배추 800g · 정상가', 'search.ssg?query=야채'), ('양파', 4000, 8040, '양파 4kg · 정상가', 'search.ssg?query=야채'), ('대파', 500, 3280, '깐대파 500g · 정상가', 'disp/category.ssg?dispCtgId=6000213178'), ('감자', 2000, 5980, '햇감자 2kg 박스', 'disp/theme/category.ssg?dispCtgId=6000224045'), ('당근', 1000, 5200, '자연맛남 국내산 흙당근 1kg', 'item/itemView.ssg?itemId=1000784715520'), ('애호박', 200, 2980, '인큐 애호박 200g 1입 · 정상가', 'search.ssg?query=야채'), ('김치', 500, 7580, '비비고 썰은배추김치 500g', 'disp/category.ssg?dispCtgId=6000213300'), ('참치', 1500, 23700, '동원 라이트스탠다드 150g 10캔 묶음', 'item/itemView.ssg?itemId=1000708179227'), ('우동면', 2000, 9000, '한일 본고장면 200g 10개 묶음', 'search.ssg?query=우동면사리'), ('어묵', 300, 2980, '대림선 A5종이어묵 300g', 'disp/category.ssg?dispCtgId=6000213254')]
for k,qty,price,name,url in PRICE_INFO:
    ING[k]=(qty,ING[k][1],price)
# 1인분 재료 사용량. 주식이 포함된 계산용 메뉴이며 실제 사용량은 취향에 따라 달라집니다.
REC={
 '김치볶음밥':{'쌀':90,'김치':100,'달걀':1,'대파':15},
 '달걀볶음밥':{'쌀':90,'달걀':2,'당근':30,'대파':15,'양파':40},
 '참치덮밥':{'쌀':90,'참치':75,'달걀':1,'양파':50},
 '두부김치 덮밥':{'쌀':90,'두부':150,'김치':100,'양파':40},
 '돼지고기 양배추덮밥':{'쌀':90,'돼지고기':120,'양배추':120,'양파':50},
 '닭고기덮밥':{'쌀':90,'닭고기':130,'달걀':1,'양파':60},
 '감자달걀 한상':{'쌀':90,'감자':150,'달걀':2,'대파':15},
 '두부채소 한상':{'쌀':90,'두부':150,'애호박':80,'당근':30,'양파':40},
 '닭고기 채소볶음밥':{'쌀':90,'닭고기':100,'양배추':80,'당근':30,'양파':40},
 '돼지고기 김치 한상':{'쌀':90,'돼지고기':120,'김치':120,'두부':80},
 '어묵볶음우동':{'우동면':200,'어묵':80,'양배추':120,'양파':50,'당근':20},
 '닭고기 볶음우동':{'우동면':200,'닭고기':100,'양배추':100,'양파':40},
 '참치김치 덮밥':{'쌀':90,'참치':75,'김치':100,'양파':40},
 '두부달걀 덮밥':{'쌀':90,'두부':100,'달걀':2,'양파':50},
}

def evaluate(menus,people,stock,prices,packs):
    need={k:0 for k in ING}
    for menu in menus:
        for k,v in REC[menu].items():need[k]+=v*people
    rows=[];total=0;surplus_value=0
    for k,n in need.items():
        if n==0:continue
        size=packs[k];price=prices[k];available=stock[k]
        missing=max(0,n-available)
        count=math.ceil(missing/size) if missing else 0
        extra=count*size-missing
        cost=count*price
        total+=cost
        surplus_value+=extra/size*price
        rows.append({'재료':k,'단위':ING[k][1],'필요량':n,'보유량':available,
                     '구매 포장':count,'구매량':count*size,'구매 후 잉여':extra,'금액':cost})
    return {'menus':menus,'rows':rows,'total':total,'surplus':surplus_value}

def optimize(candidates,meals,people,stock,prices,packs,budget,mode):
    if math.comb(len(candidates),meals)>100000:
        raise ValueError('추천 후보가 너무 많습니다. 메뉴 후보를 줄여 주세요.')
    results=[evaluate(c,people,stock,prices,packs) for c in itertools.combinations(candidates,meals)]
    # 예산 안 조합을 우선. 없으면 초과 금액이 가장 적은 조합부터.
    def key(r):
        excess=max(0,r['total']-budget)
        rest=(r['surplus'],r['total']) if mode=='남는 재료 줄이기' else (r['total'],r['surplus'])
        return (excess>0,excess,*rest)
    return sorted(results,key=key)[:3]

def recipe_search(query):
    response=requests.get('https://www.10000recipe.com/recipe/list.html',params={'q':query},timeout=20)
    response.raise_for_status()
    soup=BeautifulSoup(response.text,'html.parser')
    found=[]
    for card in soup.select('.common_sp_list_li'):
        link=card.select_one('a.common_sp_link')
        title=card.select_one('.common_sp_caption_tit')
        if link and title and re.fullmatch(r'/recipe/\d+',link.get('href','')):
            found.append({'title':title.get_text(' ',strip=True),'url':'https://www.10000recipe.com'+link['href']})
    return found[:24]

def recipe_lookup(url):
    if not re.fullmatch(r'https://www\.10000recipe\.com/recipe/\d+',url):
        raise ValueError('지원하지 않는 주소입니다.')
    response=requests.get(url,timeout=20);response.raise_for_status()
    soup=BeautifulSoup(response.text,'html.parser')
    for node in soup.select('script[type="application/ld+json"]'):
        try: obj=json.loads(node.get_text())
        except (ValueError,TypeError):continue
        items=obj if isinstance(obj,list) else [obj]
        for item in items:
            if isinstance(item,dict) and item.get('recipeIngredient'):
                # 구조화 데이터에 재료량이 빠지는 페이지는 화면의 재료 목록으로 보완.
                ingredients=[]
                for li in soup.select('.ready_ingre3 li'):
                    clone=BeautifulSoup(str(li),'html.parser')
                    for tag in clone.select('button, .btn_list, .ingre_list_btn'):tag.decompose()
                    line=clone.get_text(' ',strip=True).replace('구매','').strip()
                    if line:ingredients.append(line)
                if ingredients:item['recipeIngredient']=ingredients
                if not item.get('recipeYield'):
                    servings=soup.select_one('.view2_summary_info1')
                    if servings:item['recipeYield']=servings.get_text(' ',strip=True)
                return item
    raise ValueError('원문에서 재료 정보를 찾지 못했습니다.')

EXTRA_PRICES = [('고추장', 1000, 'g', 4380, '노브랜드 정성깃든고추장', 'disp/category.ssg?dispCtgId=6000215289'), ('간장', 900, 'mL', 3280, '노브랜드 풍미 더한 양조간장', 'disp/category.ssg?dispCtgId=6000215288'), ('국간장', 500, 'mL', 4820, '청정원 햇살담은 국간장', 'disp/category.ssg?dispCtgId=6000215288'), ('설탕', 2000, 'g', 3580, '노브랜드 하얀설탕', 'disp/category.ssg?dispCtgId=6000215330'), ('고춧가루', 110, 'g', 5980, '피코크 국산 고운 고춧가루', 'disp/category.ssg?dispCtgId=6000215290'), ('버터', 450, 'g', 11580, '서울우유 버터', 'disp/category.ssg?dispCtgId=6000213553'), ('슬라이스치즈', 288, 'g', 3980, '5K프라이스 슬라이스치즈', 'disp/category.ssg?dispCtgId=6000213544'), ('모짜렐라치즈', 1000, 'g', 16980, '서울우유 슈레드 모짜렐라치즈', 'disp/category.ssg?dispCtgId=6000213544'), ('새우젓', 1000, 'g', 17900, '강화도 특등급 추젓 · 판매가 기준', 'item/itemView.ssg?itemId=1000739616485'), ('된장', 500, 'g', 3380, '신송 된장', 'search.ssg?query=시골된장'), ('소금', 500, 'g', 4280, '청정원 천일염 가는소금', 'search.ssg?query=청정원천일염가는소금'), ('청양고추', 150, 'g', 2180, '청양고추 150g', 'disp/category.ssg?dispCtgId=6000213193'), ('스파게티면', 500, 'g', 3280, '오뚜기 프레스코 스파게티', 'item/itemView.ssg?itemId=1000544935123')]
for k,qty,unit,price,name,url in EXTRA_PRICES:
    ING[k]=(qty,unit,price)
    PRICE_INFO.append((k,qty,price,name,url))

def convert_ingredient(line):
    # 원문에 명시된 중량/개수만 변환. 재료명 속 숫자는 사용하지 않습니다.
    text=str(line).replace(',', '').replace('½','1/2').replace('¼','1/4').replace('¾','3/4')
    text=re.sub(r'(?<=\d)\s*/\s*(?=\d)','/',text)
    aliases={'돼지고기':['돼지고기','목살','삼겹살','앞다리살'],'닭고기':['닭고기','닭다리살','닭가슴살'],
             '쌀':['생쌀'],'참치':['참치'],'달걀':['달걀','계란','달걀노른자','달걀흰자'],'간장':['간장','진간장','양조간장'],'김치':['김치','묵은지']}
    aliases.update({'스파게티면':['스파게티면','스파게티 면','파스타면','파스타 면'],'고춧가루':['고춧가루','고추가루'],'슬라이스치즈':['슬라이스치즈','슬라이스 치즈','체다치즈'],'모짜렐라치즈':['모짜렐라','모차렐라']})
    key=next((k for k in sorted(ING,key=len,reverse=True) if any(x in text for x in aliases.get(k,[k]))),None)
    if not key:return None,0,'가격 미등록 · 구매 목록에서 별도 확인'
    match=re.search(r'(\d+/\d+|\d+(?:\.\d+)?)\s*(kg|킬로그램|g|그램|개|대|모|캔|봉|줌|큰술|작은술|T|t|컵|ml|mL)',text)
    if not match:return key,0,'분량 불명확'
    raw,unit=match.groups()
    if '/' in raw:
        n,d=raw.split('/');value=float(n)/float(d) if float(d) else 0
    else:value=float(raw)
    if unit in ['kg','킬로그램']:return key,value*1000,'원문 중량'
    if unit in ['g','그램']:
        return (key,value,'원문 중량') if ING[key][1]=='g' else (key,0,'질량·부피 단위가 달라 계산 제외')
    if unit.lower()=='ml':
        return (key,value,'원문 부피') if ING[key][1]=='mL' else (key,0,'부피·질량 단위가 달라 계산 제외')
    if unit=='개' and key=='달걀':return key,value,'원문 개수'
    # 대략값은 사용자 입력 대신 앱이 적용하되 근거와 불확실성 공개.
    grams={'양파':200,'대파':100,'당근':150,'감자':180,'애호박':200,'양배추':1000,'달걀':1,'청양고추':10}
    factors={'모':300 if key=='두부' else None,'캔':150 if key=='참치' else None,
             '봉':ING[key][0],'줌':50,'큰술':15,'작은술':5,'T':15,'t':5,'컵':200}
    factor=(100 if key=='대파' else None) if unit=='대' else grams.get(key) if unit=='개' else factors.get(unit)
    if factor:return key,value*factor,'가정 환산 · 실제 크기·밀도 차이 있음'
    return key,0,'환산 불가'


def main():
    st.set_page_config(page_title='우리 집 장바구니',page_icon='🛒',layout='centered')
    st.markdown("""<style>
    .stApp{background:#f6f8f3;color:#243c32}
    .block-container{max-width:590px;padding:2rem 1.15rem 4rem}
    h1{font-size:1.9rem!important;letter-spacing:-1.2px;color:#234c3b}
    h3{font-size:1.15rem!important;margin-top:1.3rem!important}
    button{min-height:46px;border-radius:13px!important}
    [data-testid="stMetric"]{background:#e5efe2;padding:20px;border-radius:20px;border:1px solid #d2dfcd}
    [data-testid="stMetricValue"]{font-size:2rem;font-weight:750;color:#245739}
    [data-testid="stForm"]{background:white;border-radius:20px;border:1px solid #e1e7dd;padding:18px}
    .hero{padding:6px 0 18px}.eyebrow{font-size:12px;letter-spacing:2px;color:#69826d;font-weight:bold}
    .hero p{color:#69796c;line-height:1.6;font-size:14px}
    @media(max-width:600px){.block-container{padding-top:1.3rem}h1{font-size:1.6rem!important}}
    </style>""",unsafe_allow_html=True)
    st.markdown('<div class="hero"><div class="eyebrow">FAMILY TABLE · MARKET PLAN</div><h1>우리 집 장바구니 🥬</h1><p>먹고 싶은 요리만 골라요.<br>필요한 재료를 합치고, 구매액과 남는 양을 함께 정리해요.</p></div>',unsafe_allow_html=True)
    people=st.number_input('몇 명이 먹나요?',1,10,3)
    with st.form('search'):
        q=st.text_input('먹고 싶은 메뉴',placeholder='예: 김치찌개')
        go=st.form_submit_button('검색',use_container_width=True)
    if go and q.strip():
        try:
            with st.spinner('검색 중…'):st.session_state['hits']=recipe_search(q.strip())
            if not st.session_state['hits']:st.info('다른 이름으로 검색해 주세요.')
        except requests.RequestException:st.error('검색 사이트 연결이 어렵습니다. 잠시 후 다시 시도해 주세요.')
    hits=st.session_state.get('hits',[])
    if hits:
        pick=st.selectbox('요리 선택',range(len(hits)),format_func=lambda i:hits[i]['title'])
        if st.button('＋ 이 요리 담기',type='primary',use_container_width=True):
            try:
                with st.spinner('재료를 가져오는 중…'):
                    recipe=recipe_lookup(hits[pick]['url'])
                cart=st.session_state.setdefault('cart',[])
                if any(x['url']==hits[pick]['url'] for x in cart):
                    st.info('이미 담은 요리예요. 인원을 바꾸면 필요한 양이 함께 바뀝니다.')
                else:
                    cart.append({'recipe':recipe,'url':hits[pick]['url']})
                    st.toast('장바구니에 담았어요 🥬')
            except (requests.RequestException,ValueError):st.error('재료를 읽지 못했습니다. 다른 레시피를 선택해 주세요.')
    cart=st.session_state.get('cart',[])
    if cart and st.session_state.get('parser_version') != 4:
        refreshed=[]
        try:
            for entry in cart:
                refreshed.append({'recipe':recipe_lookup(entry['url']),'url':entry['url']})
            st.session_state['cart']=refreshed
            st.session_state['parser_version']=4
            cart=refreshed
        except (requests.RequestException,ValueError):
            st.error('기존 레시피를 다시 읽지 못했습니다. 잠시 후 다시 실행해 주세요.')
            return

    if not cart:
        st.info('먹고 싶은 요리를 검색해서 담으면 아래에 장보기 결과가 바로 나옵니다.')
        return
    st.markdown('### 담은 요리')
    for i,item in enumerate(cart):
        a,b=st.columns([5,1]);a.write(item['recipe'].get('name','요리'))
        if b.button('삭제',key=f'del_{i}'):
            cart.pop(i);st.rerun()
    need={k:0.0 for k in ING};notes=[];missing=[];sources=[]
    for item in cart:
        r=item['recipe'];yield_str=str(r.get('recipeYield',''))
        n=re.search(r'\d+(?:\.\d+)?',yield_str)
        servings=float(n.group()) if n and float(n.group())>0 else None
        if servings is None:
            st.warning(r.get('name','요리')+' · 원문 기준 인원을 확인하지 못했습니다. 아래에서 인원만 확인해주세요.')
            servings=st.number_input('원문 레시피는 몇 인분인가요?',min_value=1,max_value=30,value=None,key='servings_'+item['url'])
            if servings is None:
                missing.extend(str(x)+' · 기준 인원 확인 필요' for x in r.get('recipeIngredient',[]))
                continue
        for line in r.get('recipeIngredient',[]):
            key,qty,reason=convert_ingredient(line)
            if key and qty>0:
                need[key]+=qty*people/servings
                notes.append(str(line)+' → '+reason)
            else:missing.append(str(line)+' · '+reason)
        sources.append((r.get('name','원문'),item['url']))
    with st.expander('집에 있는 재료 빼기 · 가격 바꾸기'):
        base=[{'재료':k,'단위':v[1],'보유량':0,'포장량':v[0],'가격':v[2]} for k,v in ING.items() if need[k]>0]
        data=st.data_editor(base,hide_index=True,use_container_width=True,disabled=['재료','단위'],
           column_config={c:st.column_config.NumberColumn(min_value=1 if c=='포장량' else 0,required=True) for c in ['보유량','포장량','가격']}) if base else []
    total=0;rows=[]
    for row in data:
        if any(row.get(c) is None for c in ['보유량','포장량','가격']) or row['포장량']<=0:
            st.warning('포장량은 0보다 크게 입력하세요.');return
        shortage=max(0,need[row['재료']]-row['보유량']);count=math.ceil(shortage/row['포장량'])
        cost=count*row['가격'];total+=cost
        rows.append({'재료':row['재료'],'구매':f"{count}포장",'예상금액':round(cost),'새로 사서 남는 양':f"{max(0,count*row['포장량']-shortage):.1f}{row['단위']}"})
    if not rows:
        st.warning('구매 금액을 계산하지 못했어요. 아래 준비 목록은 누락 없이 확인하세요. 0원 또는 무료라는 뜻이 아닙니다.')
    else:
        st.metric('일부 재료 예상액' if missing else '예상 추가 구매액',f'{total:,.0f}원')
        if total==0:st.caption('계산된 재료는 입력한 보유량으로 충당됩니다. 미계산 항목이 있으면 별도 구매가 필요할 수 있어요.')
    if missing and rows:st.caption(f'전체 금액이 아니에요. 아래 목록에서 미계산 재료 {len(dict.fromkeys(missing))}개를 확인하세요.')
    if any('가정' in n for n in notes):st.caption('개·모·줌 등은 앱의 대략 환산값을 적용했습니다. 정확한 무게는 원문 또는 제품에서 확인하세요.')
    st.markdown('### 장보기 · 남는 양')
    for row in rows:
        st.checkbox(f"{row['재료']} · {row['구매']} · {row['예상금액']:,}원",key='check_'+row['재료']+'_'+str(round(need[row['재료']],2))+'_'+str(people))
        st.caption('새로 구매해서 남는 양: '+row['새로 사서 남는 양'])
    if missing:
        st.markdown('#### 매장에서 확인할 재료')
        for entry in dict.fromkeys(missing):
            label, sep, reason = entry.rpartition(' · ')
            st.checkbox((label if sep else entry) + ' · 금액 미계산', key='pending_'+hashlib.sha256(entry.encode()).hexdigest(), help=reason if sep else None)
    text='우리 집 장보기 · '+str(people)+'인\n메뉴: '+', '.join(x['recipe'].get('name','요리') for x in cart)+'\n\n'
    text+='\n'.join('□ '+x['재료']+' / '+x['구매']+' / '+format(x['예상금액'],',')+'원 / 남는 양 '+x['새로 사서 남는 양'] for x in rows)
    text+='\n\n'+('계산 가능한 재료 합계: '+format(total,',.0f')+'원' if rows else '금액 계산 불가 · 0원이 아닙니다')
    if missing:text+='\n⚠ 전체 금액이 아닙니다. 추가 확인: '+' / '.join(missing)
    text+='\n가격은 고정 참고값이며 배송비 제외. 분량 환산은 추정입니다.'
    st.caption('목록을 저장해서 가족 단톡방에 보내면 같은 목록으로 장볼 수 있어요.')
    st.download_button('📥 가족에게 보낼 목록 저장',text.encode('utf-8-sig'),'장보기.txt',use_container_width=True)
    with st.expander('레시피 · 환산 기준 · 가격 출처'):
        for name,url in sources:st.markdown(f'[{name}]({url})')
        for note in notes:st.write(note)
        st.caption('가정: 양파200g/개, 대파100g/개, 당근150g/개, 감자180g/개, 애호박200g/개, 양배추1kg/개, 두부300g/모, 참치150g/캔, 줌50g, 큰술15g, 작은술5g, 컵200g. 재료별 밀도·크기에 따라 차이가 큽니다. 봉은 등록된 구매 포장량을 가정합니다.')
        st.caption('가격은 이전에 수집한 공개 판매 참고값이며 실시간 시장 평균이 아닙니다. 배송비 제외. 메뉴·보유량은 접속 세션에서만 유지되고 가족 휴대폰 간 동기화되지 않습니다.')
        st.caption('추가 조사 가격 포함 총 '+str(len(ING))+'종. 2026.11.02 공개 검색 결과 기준이며 과거 행사 정보가 섞일 수 있습니다. 다진마늘은 검색 자료의 1kg/100g 표기가 충돌해 채택하지 않았습니다. 등록되지 않은 재료의 가격은 추측하지 않습니다.')
        for k,qty,price,name,url in PRICE_INFO:st.markdown(f'{k} · {qty}{ING[k][1]} · {price:,}원 · [판매정보](https://emart.ssg.com/{url})')



if __name__=='__main__':main()
