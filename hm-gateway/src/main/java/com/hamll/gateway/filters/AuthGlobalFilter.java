package com.hamll.gateway.filters;

import cn.hutool.core.text.AntPathMatcher;
import com.hamll.gateway.config.AuthProperties;
import com.hamll.gateway.util.JwtTool;
import lombok.RequiredArgsConstructor;
import org.springframework.cloud.gateway.filter.GatewayFilterChain;
import org.springframework.cloud.gateway.filter.GlobalFilter;
import org.springframework.core.Ordered;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatus;
import org.springframework.http.server.reactive.ServerHttpRequest;
import org.springframework.http.server.reactive.ServerHttpResponse;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

import java.util.List;

@Component
@RequiredArgsConstructor
public class AuthGlobalFilter implements GlobalFilter, Ordered {
    private final AuthProperties authProperties;
    private final JwtTool jwtTool;
    private final AntPathMatcher antPathMatcher;

    @Override
    public Mono<Void> filter(ServerWebExchange exchange, GatewayFilterChain chain) {
        //获取请求
        ServerHttpRequest request = exchange.getRequest();
        //浏览器的跨域预检请求（OPTIONS）不带 token，必须直接放行，否则前端一个请求都发不出去
        if (HttpMethod.OPTIONS.equals(request.getMethod())) {
            return chain.filter(exchange);
        }
        //判断是否拦截
        if(isExclude(request.getPath().toString())){
            return chain.filter(exchange);
        }
        //获取token
        String token=null;
        List<String> headers=request.getHeaders().get("authorization");
        if(headers!=null&&headers.size()>0){
            token=headers.get(0);
        }
        //解析校验token
        Long userId=null;
        try {
            userId=jwtTool.parseToken(token);
        } catch (Exception e) {
            //拦截 设置响应码401
            ServerHttpResponse response=exchange.getResponse();
            response.setStatusCode(HttpStatus.UNAUTHORIZED);
            return response.setComplete();
        }
        //传递用户信息
        String userInfo=userId.toString();
        ServerWebExchange ex =exchange.mutate().request(
                b->b.header("user-Info", userInfo).build()
        ).build();
        //放行
        return chain.filter(ex);
    }

    private boolean isExclude(String antPath) {
        for (String pathPattern : authProperties.getExcludePaths()) {
            if(antPathMatcher.match(pathPattern, antPath)){
                return true;
            }
        }
        return false;
    }

    @Override
    public int getOrder() {
        return 0;
    }
}
