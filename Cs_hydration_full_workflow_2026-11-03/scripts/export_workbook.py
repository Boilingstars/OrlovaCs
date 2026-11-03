#!/usr/bin/env python3
"""Export all ion CSV tables to one Excel workbook, leaving unavailable results empty."""
import csv,os,tempfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
IONS=('Li','Na','K','Rb','Cs')
HEAD=['n','структура','энергия_Ha','радиус_A','cos(x)','#water']


def rows_from_cs():
    rows=[]
    for n in range(4,15):
        base=ROOT/'runs'/f'Cs_{n:02d}'/'full_100'
        energy=base/'verified/free_sorted_metadata.csv'
        mdatom=base/'mdatom/mdatom_counts.csv'
        if not energy.is_file() or not mdatom.is_file():continue
        with energy.open(encoding='utf-8',newline='') as fh:e=list(csv.DictReader(fh))
        with mdatom.open(encoding='utf-8',newline='') as fh:m=list(csv.DictReader(fh))
        if len(e)!=len(m):raise ValueError(f'Cs n={n}: mismatched energy/MDAtom lengths')
        for en,md in zip(e,m):
            if int(en['sorted_frame'])!=int(md['sorted_frame']):raise ValueError(f'Cs n={n}: frame mismatch')
            rows.append([n,en['source'],float(en['energy_hartree']),float(md['radius_mdatom_A']),float(md['orientation_cos_mdatom']),float(md['coordination_mdal'])])
    return rows


def main():
    import xlsxwriter
    tables=ROOT/'analysis/ion_tables'
    tables.mkdir(parents=True,exist_ok=True)
    cs=rows_from_cs()
    cs_path=tables/'Cs.csv'
    with cs_path.open('w',encoding='utf-8-sig',newline='') as fh:
        w=csv.writer(fh);w.writerow(HEAD);w.writerows(cs)
    (ROOT/'runs').mkdir(exist_ok=True)
    fd,tmp=tempfile.mkstemp(prefix='_mdatom_',suffix='.xlsx',dir=ROOT/'runs')
    os.close(fd)
    try:
        wb=xlsxwriter.Workbook(tmp)
        hstyle=wb.add_format({'bold':True,'font_color':'white','bg_color':'#17365d','align':'center','border':1})
        num=wb.add_format({'num_format':'0.0000000000'})
        rad=wb.add_format({'num_format':'0.0000'})
        small=wb.add_format({'num_format':'0.000'})
        for ion in IONS:
            sheet=wb.add_worksheet(ion)
            sheet.freeze_panes(1,0)
            sheet.set_column('A:A',8)
            sheet.set_column('B:B',28)
            sheet.set_column('C:C',20,num)
            sheet.set_column('D:E',16,rad)
            sheet.set_column('F:F',14,small)
            sheet.write_row(0,0,HEAD,hstyle)
            last_row=0
            path=tables/f'{ion}.csv'
            if not path.is_file():continue
            with path.open(encoding='utf-8-sig',newline='') as fh:
                rd=csv.DictReader(fh)
                for k,row in enumerate(rd,1):
                    last_row=k
                    sheet.write_number(k,0,int(row['n']))
                    sheet.write(k,1,row['структура'])
                    for c,name in enumerate(HEAD[2:],2):
                        if row[name]!='':sheet.write_number(k,c,float(row[name]))
            if last_row>0:sheet.autofilter(0,0,last_row,5)
        wb.close()
        os.replace(tmp,ROOT/'runs/MDAtom_water.xlsx')
    finally:
        if os.path.isfile(tmp):os.remove(tmp)
    print(f'Excel: {ROOT/"runs/MDAtom_water.xlsx"}; Cs structures={len(cs)}')

if __name__=='__main__':main()
