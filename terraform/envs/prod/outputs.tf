output "public_ip" {
  description = "ゲートウェイのパブリック IP"
  value       = module.gateway.public_ip
}

output "admin_username" {
  value = module.gateway.admin_username
}
