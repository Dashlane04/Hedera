#!/usr/bin/env python3
"""Publish a measured project-upgrade summary and optional PDF (ReportLab)."""
import argparse
from collections import defaultdict
import csv
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import statistics
from xml.sax.saxutils import escape

ROOT=Path(__file__).resolve().parents[1]


def read(path):
    with path.open(newline='',encoding='utf-8') as f:return list(csv.DictReader(f))


def collect(a):
    runs={}
    for key in ['dynamic','control','smoke','integration','regression']:
        directory=getattr(a,key)
        runs[key]=[(p.parent,json.loads(p.read_text())) for p in sorted(directory.rglob('summary.json'))]
    assert len(runs['dynamic'])==12 and len(runs['control'])==6,'complete primary studies first'
    assert len(runs['smoke'])==9 and len(runs['integration'])==8 and len(runs['regression'])==3,'complete acceptance/regression first'
    acceptance=json.loads((a.analysis/'acceptance.json').read_text())
    assert all(c['passed'] for c in acceptance['checks'])
    oracle=read(a.oracle/'oracle-comparisons.csv');live=read(a.oracle/'live-comparisons.csv')
    assert len(oracle)==260 and len(live)==20
    summary={}
    for steps in [0,10,100,1000]:
        rows=[r for r in oracle if int(r['steps'])==steps]
        summary[steps]=dict(n=len(rows),optimal=statistics.mean(int(r['optimal']) for r in rows),
                            mean_gap=statistics.mean(float(r['absolute_gap']) for r in rows),max_gap=max(float(r['absolute_gap']) for r in rows))
    dynamic={}
    for alg in ['ecmp','gff','sa','nonblocking']:
        rows=[s for _,s in runs['dynamic'] if s['algorithm']==alg]
        dynamic[alg]=dict(n=len(rows),goodput=statistics.mean(s['window_goodput_mbps'] for s in rows))
    # Preserve the exact legacy packet outcomes, independent of added CSV fields.
    for directory,s in runs['regression']:
        old=a.before/directory.name;before=json.loads((old/'summary.json').read_text())
        for key in ['window_goodput_mbps','received_payload_bytes','route_changes','completed','detected_large']:
            assert before[key]==s[key],(directory.name,key)
    snapshots=json.loads((a.oracle/'live-snapshot.json').read_text())
    assert snapshots['planned_energy']+1e-8 >= float(live[0]['oracle_energy'])
    info=dict(date='2026-10-29',simulation_runs={k:len(v) for k,v in runs.items()},
              oracle_comparisons=len(oracle),live_comparisons=len(live),oracle_by_budget=summary,
              dynamic=dynamic,live_snapshot=snapshots,
              replay=dict(path=str(a.replay),offline_logic_renders=3*sum(s['flows'] for _,s in runs['dynamic']+runs['control']),browser_visual_review=False,
                          limitation='In-app browser policy blocked file://; no alternate browser or network workaround was used.'),
              scope='Fixture replication and independent ns-3 extension; no full numerical reproduction of Hedera.')
    hashes={}
    for folder in ['sim','scripts','tests','web']:
        for p in sorted((ROOT/folder).iterdir()):
            if p.is_file() and p.suffix in {'.h','.cc','.py','.sh','.mjs','.txt','.html'}:
                hashes[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    hashes['CMakeLists.txt']=hashlib.sha256((ROOT/'CMakeLists.txt').read_bytes()).hexdigest()
    raw={}
    for directory in [a.dynamic,a.control,a.oracle,a.smoke,a.integration,a.regression]:
        for p in sorted(directory.rglob('*')):
            if p.is_file() and p.suffix in {'.csv','.json'} and 'source' not in p.parts:
                raw[os.path.relpath(p,ROOT)]=hashlib.sha256(p.read_bytes()).hexdigest()
    info['source_sha256']=hashes;info['data_sha256']=raw
    return info,runs


def markdown(a,info,runs):
    rel=lambda p:Path(os.path.relpath(p,a.markdown.parent)).as_posix()
    text=['# Kết quả nâng cấp project Hedera','',
          'Cập nhật **29/10/2026**. Đây là kết quả của source được chia module mới; dữ liệu 230 run trước đó được giữ nguyên.','',
          '## Phần đã hoàn tất','',
          '- Tách data plane, monitoring, control plane, workload và telemetry; thêm queue và detector thuần C++ để kiểm thử riêng.',
          '- Workload ba pha, source stop từng flow, cohort, log pha và source events; giữ khả năng đọc CSV cũ.',
          '- FIFO/coalesce với snapshot ID/time, kiểm tra tuổi, FIN/RST/idle và thống kê backlog lúc dừng.',
          '- Metric chung: per-flow goodput, conditional p95 FCT, fairness population, retransmission/drop, route changes và tuổi cài đặt.',
          '- Oracle exact cùng state space SA, thêm cầu nối xuất snapshot từ log controller thực.',
          '- Replay HTML nhúng dữ liệu, chọn run/flow/time, xem utilization, đường cài/proposal, goodput và events.','',
          '## Kiểm tra đã chạy','',
          '| Bộ | Số run/đối chiếu | Phạm vi |','|---|---:|---|',
          '| Dynamic | 12 | Một fixture, 4 phương pháp × 3 seed |',
          '| Control lifecycle | 6 | FIFO/coalesce, quá hạn, flow kết thúc trước cài |',
          '| Benchmark acceptance | 9 | Reference, Poisson, sustained, measured demand, diagnostics thụ động |',
          '| Integration | 8 | CSV locality, 128-host single flow, delay, hotspot chưa xong |',
          '| Regression demo | 3 | ECMP/GFF/SA giữ nguyên packet outcomes so với bản trước |',
          '| Oracle synthetic | 260 | 13 snapshot × 4 ngân sách × 5 seed |',
          '| Oracle từ log thật | 20 | Snapshot 8 flow tại 3,2 s, 576 state hợp lệ |','',
          'Tổng **38 run mạng mới**: 18 run mở rộng nghiên cứu và 20 run acceptance/regression; không cộng 280 đối chiếu core vào số run ns-3. CTest có hai executable đã qua; Python có hai test method về metric. Replay qua kiểm tra logic/DOM contract với 18 run và 411 tổ hợp flow/thời điểm. Đây không phải xác nhận render trong trình duyệt.','',
          '## Tải động','', '| Phương pháp | Số lần chạy | Mean goodput Mbit/s |','|---|---:|---:|']
    for alg,r in info['dynamic'].items():text.append(f'| {alg} | {r["n"]} | {r["goodput"]:.3f} |')
    text+=['','Fixture 16 host, 20 Mbit/s, source kết thúc ở 9 s, drain 2 s; cửa sổ đo 0,8–8,8 s; polling 100 ms và MinRTO 300 ms. Bốn flow background tồn tại suốt run; bốn flow burst bắt đầu 3 s và nguồn dừng 6 s.','',
           'Traffic cố định giữa seed; ECMP/GFF lặp xác định, seed thay RNG SA. Đây là kiểm tra cơ chế và tính tái lập, không phải ba traffic matrix độc lập hay bằng chứng thống kê cho mọi workload.',
           'Goodput background ECMP giảm trong burst và hồi phục chậm do buffer/transport; source stop không có nghĩa dữ liệu biến mất ngay. Mốc recovery dùng ba bucket liên tiếp đạt 95% baseline và công bố trường hợp không quan sát suy giảm trước đó.','',
           f'![Tải động]({rel(a.analysis/"dynamic-timeline.png")})','',
           '## Hàng chờ điều khiển','',
           '| Case | Submitted | Installed | Replaced | Expired | Flow install bị bỏ vì inactive | Pending khi dừng |',
           '|---|---:|---:|---:|---:|---:|---:|']
    for directory,s in runs['control']:
        text.append('| '+directory.name+' | '+' | '.join(str(s[k]) for k in ['plans_submitted','plans_installed','plans_replaced','plans_expired','inactive_install_skips','pending_plans_at_stop'])+' |')
    text+=['','Delay 250 ms và interval 100 ms tạo backlog có chủ đích. Coalesce thay kế hoạch chờ, không hủy kế hoạch đang phục vụ. Case finished-before-install dùng delay 400 ms và bỏ được một lần cài cho flow đã hết active. Case age-limit bỏ 30 kế hoạch quá hạn. Pending được giữ trong thống kê, không coi là kế hoạch đã cài.',
           'Kế hoạch rỗng vẫn chiếm một lượt phục vụ trong mô hình này. Reservation/mapping của scheduler và đường đã cài được phân biệt; độ trễ là hằng cấu hình, chưa mô hình chi phí OpenFlow theo số rule.','',
           '## Oracle exact','', '| SA steps | Số so sánh | Tỷ lệ đạt H* | Mean gap | Max gap |','|---|---:|---:|---:|---:|']
    for steps,r in info['oracle_by_budget'].items():text.append(f'| {steps} | {r["n"]} | {100*r["optimal"]:.2f}% | {r["mean_gap"]:.6f} | {r["max_gap"]:.6f} |')
    text+=['','Các tỷ lệ chỉ thuộc tập snapshot nhỏ đã chọn. H* tối ưu tổng phần demand vượt capacity trong cùng mapping space của SA; không phải optimum TCP goodput. Có một case demand > NIC gắn nhãn synthetic. Không chia gap cho H* vì H* có thể bằng 0.','',
           f'Snapshot từ run SA lúc **{info["live_snapshot"]["snapshot_time"]} s** có **{info["live_snapshot"]["flows"]} flow**; oracle duyệt **{live_states(a)} state**, H* = {float(read(a.oracle/"live-comparisons.csv")[0]["oracle_energy"]):g}; planned H trong log = {info["live_snapshot"]["planned_energy"]:g}. Cold-start SA trong oracle study được phân biệt với warm-start plan đã ghi trong run mạng.','',
           f'![Oracle]({rel(a.analysis/"oracle-quality.png")})','',
           '## So với paper và các giới hạn còn lại','',
           f'Xem [bảng đối chiếu]({rel(ROOT/"docs/paper-comparison.vi.md")}) và [kiến trúc/module]({rel(ROOT/"docs/architecture.vi.md")}). Giữ pipeline Hedera nhưng dùng packet-level ns-3 và có các mở rộng queue, oracle, metric và replay. Chưa có OpenFlow packets, TCAM, link failure/failover, quy mô 1.024/8.192 host hoặc chứng nhận mức 96% optimal goodput.','',
           '## Mở kết quả và chạy lại','',
           f'- [Replay HTML]({rel(a.replay)}) — mở ngoại tuyến trong trình duyệt hỗ trợ HTML/SVG/JavaScript.',
           f'- [CSV metric chính từ dữ liệu cũ]({rel(ROOT/"results/upgrade-main-metrics/benchmark-aggregate.csv")}) — tính vào output mới, không chạy lại hoặc sửa 100 run Main16.',
           f'- [Acceptance receipt]({rel(a.analysis/"acceptance.json")}) và [source/data hashes]({rel(a.analysis/"provenance.json")}).','',
           '```bash','cd /path/to/Hedera','bash scripts/run-upgrade-study.sh','```','',
           '**Giới hạn kiểm tra giao diện:** trình duyệt tích hợp chặn URL `file://`. Không dùng trình duyệt khác hoặc server để lách chặn. Đã kiểm tra script, dữ liệu, SVG geometry hữu hạn, đổi run/flow/time và phát/dừng bằng harness ngoại tuyến; chưa xác nhận bố cục/render trên browser thật. Báo cáo LaTeX đã biên dịch thành công bằng compiler của ứng dụng.','']
    a.markdown.parent.mkdir(parents=True,exist_ok=True);a.markdown.write_text('\n'.join(text),encoding='utf-8')


def live_states(a):return int(read(a.oracle/'live-comparisons.csv')[0]['states'])


def pdf(a,info,runs):
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,PageBreak,Image
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.graphics.shapes import Drawing,Rect,String,Line,Polygon
    fonts=ROOT/'report/hedera-ns3/fonts'
    pdfmetrics.registerFont(TTFont('DV',str(fonts/'DejaVuSans.ttf')))
    pdfmetrics.registerFont(TTFont('DVB',str(fonts/'DejaVuSans-Bold.ttf')))
    pdfmetrics.registerFontFamily('DV',normal='DV',bold='DVB',italic='DV',boldItalic='DVB')
    ink=colors.HexColor('#183638');teal=colors.HexColor('#277a70');muted=colors.HexColor('#687e7a');grid=colors.HexColor('#dce4df')
    style=ParagraphStyle('body',fontName='DV',fontSize=10,leading=15,textColor=ink,spaceAfter=9)
    small=ParagraphStyle('small',parent=style,fontSize=8.5,leading=12)
    heading=ParagraphStyle('heading',parent=style,fontName='DVB',fontSize=19,leading=25,spaceAfter=14)
    sub=ParagraphStyle('sub',parent=style,fontName='DVB',fontSize=11,leading=16,spaceBefore=8)
    width=475;story=[]
    def para(text,kind=style):return Paragraph(text,kind)
    def title(text):story.append(para(text.replace('\n','<br/>'),heading))
    def p(text):story.append(para(text))
    def table(headers,rows,widths):
        data=[[para(escape(str(x)),small) for x in headers]]+[[para(escape(str(x)),small) for x in row] for row in rows]
        t=Table(data,colWidths=widths,repeatRows=1,hAlign='LEFT')
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#edf2eb')),('VALIGN',(0,0),(-1,-1),'TOP'),('LINEBELOW',(0,0),(-1,0),.7,teal),('LINEBELOW',(0,1),(-1,-1),.35,grid),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6)]))
        story.append(t);story.append(Spacer(1,10))
    def picture(path,w=width):
        from PIL import Image as PILImage
        with PILImage.open(path) as image:h=w*image.height/image.width
        story.append(Image(str(path),width=w,height=h));story.append(Spacer(1,8))
    def page():story.append(PageBreak())
    title('Hedera trên ns-3\nKiến trúc và kết quả nâng cấp')
    p('Cập nhật 29/10/2026 · Phần mở rộng project sau bộ dữ liệu nghiên cứu ban đầu. Tài liệu này tách kết quả mới khỏi 230 run trước đó và giữ rõ phạm vi so với Hedera NSDI 2010.')
    d=Drawing(width,185)
    def box(x,y,w,label):
        d.add(Rect(x,y,w,42,fillColor=colors.HexColor('#faf8f3'),strokeColor=teal,strokeWidth=.9))
        for i,line in enumerate(label.split('\n')):d.add(String(x+w/2,y+27-i*13,line,fontName='DV',fontSize=9,textAnchor='middle',fillColor=ink))
    def arrow(x1,y1,x2,y2):
        import math
        d.add(Line(x1,y1,x2,y2,strokeColor=teal,strokeWidth=1));theta=math.atan2(y2-y1,x2-x1);size=5
        d.add(Polygon([x2,y2,x2-size*math.cos(theta-.45),y2-size*math.sin(theta-.45),x2-size*math.cos(theta+.45),y2-size*math.sin(theta+.45)],fillColor=teal,strokeColor=teal))
    box(0,126,125,'Host / TCP\nBulkSend, PacketSink');box(175,126,125,'Data plane\nECMP / fabric / queue');box(350,126,125,'Monitoring\nCounter, FIN / idle')
    box(350,48,125,'Snapshot / demand\nNatural estimator');box(175,48,125,'Control plane\nGFF hoặc SA');box(0,48,125,'Plan queue\nFIFO / coalesce / install')
    arrow(125,147,175,147);arrow(300,147,350,147);arrow(412,126,412,90);arrow(350,69,300,69);arrow(175,69,125,69)
    d.add(Line(62,90,62,108,strokeColor=teal));d.add(Line(62,108,237,108,strokeColor=teal));arrow(237,108,237,126)
    d.add(String(width/2,13,'Telemetry → Metric / Replay / Oracle: công cụ đánh giá riêng',fontName='DV',fontSize=9,textAnchor='middle',fillColor=muted))
    story.append(d)
    table(['Module','Trách nhiệm'],[
        ['Data plane','hedera-data-plane.cc: topology, routing, hash và phiên bản đường.'],
        ['Monitoring','hedera-monitoring.cc: bộ đếm và soft state quan sát tại switch.'],
        ['Control plane','hedera-control-plane.cc + hedera-controller.cc: snapshot, scheduler, queue, installer.'],
        ['Harness / evaluation','hedera-workload.cc, hedera-telemetry.cc, metric/replay scripts; không cung cấp tương lai traffic cho scheduler.']], [110,365])
    p('Cách nhóm trên bám vòng điều khiển ở §3 của paper. Evaluation là phần của đồ án. Các adapter vẫn nằm trong một process ns-3; chưa phải controller hay switch phần cứng độc lập.')
    page();title('Đối chiếu với paper gốc')
    table(['Mốc paper','Project hiện tại','Mức độ'],[
        ['§3.1: default forwarding','ECMP theo flow; hash 5-tuple hoặc destination. Khởi tạo bằng đường IPv4.','Hành vi tương ứng; backend khác'],
        ['§3.1: detector','Threshold theo tỷ lệ NIC; payload source-edge, gồm retransmission; FIN/RST/idle.','Tái hiện cơ chế'],
        ['§3.2: scheduler','Snapshot, estimator, GFF/SA và cài đường trong simulator.','Trách nhiệm tương ứng'],
        ['§4.2: estimator','Sender sharing và receiver water filling; kiểm tra Figure 4 và giới hạn NIC.','Tái hiện cơ chế'],
        ['§4.3: GFF','Reservation, giữ đường, first-fit và fallback; dùng <= với tolerance tại biên.','Có biến thể biên công bố'],
        ['§4.4: SA','Mapping đích–core, delta energy, neighbor, best và warm start; T dừng ở 1.','Có bảo vệ số học'],
        ['§5–6: thực thi / đánh giá','Packet-level ns-3 NewReno; 16/128 host trong các study đã có.','Đánh giá độc lập']], [100,255,120])
    p('<b>Phần mới của project:</b> workload theo pha và stop từng flow; hàng chờ FIFO/coalesce, giới hạn tuổi snapshot; metric chung; oracle exact cho bài toán nhỏ; replay ngoại tuyến và các kiểm tra vòng đời.')
    p('<b>Chưa có:</b> OpenFlow packets, TCAM, cập nhật phân tán từng switch, link failure, replication/failover hoặc đánh giá 1.024/8.192 host. Profile 1 Gbit/s/60 s chưa thuộc kết quả nâng cấp này.')
    p('Oracle tối ưu energy H trong state space SA. Nonblocking reference là phép đo TCP/queue. Cả hai chưa chứng nhận optimal application goodput hoặc mức 96% tối ưu của paper.')
    story.append(para('Nguồn: Al-Fares và cộng sự, Hedera, NSDI 2010, §3–6. Bảng chi tiết và source mapping: docs/paper-comparison.vi.md, docs/architecture.vi.md.',small))
    page();title('Tải thay đổi theo pha')
    p('16 host, 20 Mbit/s; run 9 s và drain 2 s. Bốn flow background chạy xuyên suốt; bốn flow burst bắt đầu ở 3 s và nguồn dừng ở 6 s. ECMP của burst được đặt có chủ đích qua core 0. Cửa sổ đo 0,8–8,8 s; MinRTO 300 ms.')
    picture(a.analysis/'dynamic-timeline.png')
    table(['Phương pháp','Số lần chạy','Mean goodput (Mbit/s)'],[[alg,r['n'],f'{r["goodput"]:.3f}'] for alg,r in info['dynamic'].items()],[155,120,200])
    p('Traffic giữ cố định giữa các seed; RNG SA thay đổi. Đây là kiểm tra fixture và tính tái lập, không phải ba traffic matrix ngẫu nhiên độc lập. Đường hình là một seed minh họa. Byte trong TCP buffer có thể tiếp tục đi sau lúc nguồn burst dừng.')
    page();title('Hàng chờ và chất lượng phục vụ')
    p('Controller phục vụ một kế hoạch tại một thời điểm. FIFO giữ mọi kế hoạch chờ; coalesce thay kế hoạch đang chờ và giữ nguyên kế hoạch in-service. Case delayed dùng service delay 250 ms, lớn hơn polling 100 ms.')
    table(['Case','Cài','Thay','Quá hạn','Bỏ flow inactive','Pending'],[[d.name.replace('-s1-',' / '),s['plans_installed'],s['plans_replaced'],s['plans_expired'],s['inactive_install_skips'],s['pending_plans_at_stop']] for d,s in runs['control']],[190,45,45,55,75,65])
    p('Mỗi delayed case có 60 snapshot. FIFO còn 29 kế hoạch khi dừng; coalesce thay 35 kế hoạch và xử lý hết backlog. Case finished-before-install bỏ một lần cài cho flow không còn active. Kế hoạch rỗng vẫn chiếm một lượt phục vụ. Thông tin FIN/idle đến từ switch, không dùng receiver completion làm oracle.')
    story.append(para('Metric bổ sung từ dữ liệu Main16 đã có',sub))
    main=read(ROOT/'results/upgrade-main-metrics/benchmark-aggregate.csv')
    finite=[r for r in main if r['case']=='finite-bijection']
    table(['Phương pháp','Conditional p95 FCT (s)','Completion'],[[r['algorithm'],f'{float(r["conditional_p95_fct_s_mean"]):.3f}',f'{100*float(r["completion_fraction_mean"]):.2f}%'] for r in finite],[155,180,140])
    p('p95 trong bảng là trung bình p95 có điều kiện của từng seed, không phải quantile gộp của toàn bộ flow. Fairness Jain chỉ dùng nhóm sustained có nguồn active trọn cửa sổ; giữ cả zero goodput và công bố population. Thiếu trace retransmission/drop được giữ null, không gán 0.')
    page();title('Oracle exact và chất lượng nghiệm SA')
    p('13 snapshot nhỏ × 4 ngân sách bước × 5 seed = 260 đối chiếu. Oracle duyệt đủ các gán core cho đích active theo bijection trong pod; phần inactive được hoàn tất theo một hoán vị chuẩn. Nếu vượt giới hạn state, hàm từ chối trước khi duyệt.')
    picture(a.analysis/'oracle-quality.png')
    table(['Steps','So sánh','Đạt H*','Mean gap','Max gap'],[[n,r['n'],f'{100*r["optimal"]:.2f}%',f'{r["mean_gap"]:.4f}',f'{r["max_gap"]:.4f}'] for n,r in info['oracle_by_budget'].items()],[70,80,95,115,115])
    p(f'Snapshot từ log SA tại 3,2 s có 8 flow; oracle duyệt {live_states(a)} state. H* = 0 và planned H trong run mạng = {info["live_snapshot"]["planned_energy"]:g}. Có thêm 20 đối chiếu cold-start SA trên snapshot này. Nghiệm warm start đang cài được phân biệt với các lần cold start trong study.')
    p('Khoảng cách dùng H_SA − H*, không chia cho H* vì optimum có thể bằng 0. Tập synthetic có một case demand vượt NIC để kiểm tra optimum dương. Kết quả 100% tại 100/1.000 bước chỉ thuộc tập nhỏ đã chọn; chưa phải bảo đảm tổng quát hoặc tỷ lệ xấp xỉ.')
    page();title('Tải trên link: bằng chứng từ data plane')
    picture(a.analysis/'link-utilization.png',w=445)
    p('Cùng thứ tự link fabric có hướng và seed. Màu là utilization đo trên wire; không phải demand hay reservation của scheduler. Các vạch 3/6 s là thời điểm cấu hình nguồn burst. Heatmap giúp đối chiếu đường đi, sự phân bố tải và goodput mà không đánh đồng các chỉ tiêu.')
    page();title('Kiểm tra, tái lập và sử dụng')
    table(['Nhóm','Đã chạy'],[
        ['Thí nghiệm mở rộng','12 dynamic + 6 control lifecycle = 18 run.'],
        ['Acceptance / regression','9 benchmark acceptance + 8 integration + 3 legacy demo = 20 run.'],
        ['Thuật toán và metric','2 executable CTest; 2 Python test method; 260 synthetic + 20 live-snapshot SA comparisons.'],
        ['Replay ngoại tuyến','18 run, 411 tổ hợp flow/time; đổi run/flow/time, play/pause, finite SVG geometry và asset độc lập.'],
        ['Dữ liệu cũ','100 Main16 run được phân tích metric vào output mới; không thay dữ liệu gốc.']], [145,330])
    p('<b>Chạy lại:</b> từ /path/to/Hedera, dùng <b>bash scripts/run-upgrade-study.sh</b>. Script chọn output mới, build/test, chạy study và export replay. File HTML chứa dữ liệu, không cần CDN/server; mở bằng trình duyệt hỗ trợ HTML/SVG/JavaScript.')
    p('<b>Đọc replay:</b> chọn run và flow, kéo thời gian hoặc nhấn Phát. Đường liền là đường đã cài; đường nét đứt là proposal gần nhất trong log, có thể đã bị thay/quá hạn. Link dùng utilization đo; measured rate và natural demand được trình bày riêng.')
    p('<b>Giới hạn kiểm tra giao diện:</b> browser tích hợp chặn file://. Đã kiểm tra logic/DOM contract ngoại tuyến; chưa xác nhận bố cục trong browser thật. Không dùng server hoặc browser khác để lách chính sách. Các PNG trong báo cáo đã được xem trực tiếp. Source LaTeX cập nhật đã biên dịch thành công bằng compiler của ứng dụng.')
    p('<b>Truy vết:</b> docs/upgrade-results.vi.md; results/upgrade-analysis/acceptance.json và provenance.json; các manifest/source snapshot riêng của từng study. Source/data SHA-256 được ghi cùng summary.')
    p('Project đã bổ sung khả năng kiểm chứng động học và chất lượng nghiệm, đồng thời giữ giới hạn tái hiện rõ ràng. Ý tưởng Hedera/GFF/SA thuộc paper gốc; phần triển khai, kiểm thử, oracle và hệ thống phân tích là công việc của đồ án.')
    a.pdf.parent.mkdir(parents=True,exist_ok=True)
    def decorate(canvas,doc):
        canvas.saveState();canvas.setFont('DV',8);canvas.setFillColor(muted)
        canvas.drawString(60,812,'HEDERA / NS-3 · PROJECT UPGRADE');canvas.drawRightString(535,812,'29/10/2026')
        canvas.setStrokeColor(grid);canvas.line(60,800,535,800);canvas.drawRightString(535,29,str(doc.page));canvas.restoreState()
    doc=SimpleDocTemplate(str(a.pdf),pagesize=(595.276,841.89),leftMargin=60,rightMargin=60,topMargin=55,bottomMargin=48,
                          title='Hedera ns-3: Kiến trúc và kết quả nâng cấp',author='Đồ án Đánh giá hiệu năng mạng')
    doc.build(story,onFirstPage=decorate,onLaterPages=decorate)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key,default in dict(dynamic='upgrade-dynamic',control='upgrade-control',oracle='upgrade-oracle',analysis='upgrade-analysis',smoke='upgrade-smoke',integration='upgrade-integration',regression='upgrade-regression',before='defense-demo').items():
        p.add_argument('--'+key,type=Path,default=ROOT/'results'/default)
    p.add_argument('--replay',type=Path,default=ROOT/'output/replay/hedera-replay.html')
    p.add_argument('--markdown',type=Path,default=ROOT/'docs/upgrade-results.vi.md')
    p.add_argument('--pdf',type=Path)
    a=p.parse_args();info,runs=collect(a)
    a.analysis.mkdir(parents=True,exist_ok=True)
    (a.analysis/'provenance.json').write_text(json.dumps(info,ensure_ascii=False,indent=2),encoding='utf-8')
    markdown(a,info,runs)
    if a.pdf:pdf(a,info,runs)
    print('Published measured upgrade summary:',a.markdown)
    if a.pdf:print('PDF:',a.pdf)


if __name__=='__main__':main()
