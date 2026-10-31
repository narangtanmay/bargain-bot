import {CHECK_NAMES} from '../negotiate.mjs';
export function verifiedDeal(summary='deal summary'){
 const result={status:'deal',quote:{supplier:'Supplier B',unit_price_eur:4.75,quantity:2000,total_eur:9500},checks:CHECK_NAMES.map(name=>({name,passed:true})),summary_markdown:summary};
 return {status:'deal',summary,result};
}
