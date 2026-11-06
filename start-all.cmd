@echo off
chcp 65001 >nul
cd /d %~dp0

echo [1/6] item-service
start "item-service"  java -jar item-service\target\item-service.jar   --spring.profiles.active=local
echo [2/6] user-service
start "user-service"  java -jar user-service\target\user-service.jar   --spring.profiles.active=local
echo [3/6] cart-service
start "cart-service"  java -jar cart-service\target\cart-service.jar   --spring.profiles.active=local
echo [4/6] trade-service
start "trade-service" java -jar trade-service\target\trade-service.jar --spring.profiles.active=local
echo [5/6] pay-service
start "pay-service"   java -jar pay-service\target\pay-service.jar     --spring.profiles.active=local
echo [6/6] hm-gateway
start "hm-gateway"    java -jar hm-gateway\target\hm-gateway.jar       --spring.profiles.active=local

echo.
echo 已启动 6 个服务（各自一个窗口），网关地址: http://localhost:8080
echo 等 40 秒左右再访问，或在 Nacos 控制台确认 6 个服务已上线。
pause
