// 姓名与顺序只用于演示展示；认证和权限始终使用服务端的原账号与角色。
export const demoIdentityNames: Readonly<Record<string, string>>={
 demo_manager:'程一舟',
 qichen_rd_head:'林岚',qichen_prd_head:'赵启铭',qichen_fin_head:'沈知微',qichen_hr_head:'顾清',qichen_adm_head:'韩朔',
 qichen_rd:'陈叙',qichen_qa:'苏晚',qichen_ops:'陆既明',
 qichen_prd:'何见山',qichen_fin:'纪云舒',qichen_hr:'白芷',qichen_adm:'任重',qichen_guest:'访客',
}

export function demoIdentityName(username?: string): string | undefined {
  return username && Object.hasOwn(demoIdentityNames, username) ? demoIdentityNames[username] : undefined
}
