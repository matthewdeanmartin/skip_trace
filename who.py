# import whois
# w = whois.whois('hynek.me')
# print(w)


import whoisit
whoisit.bootstrap()
data = whoisit.domain("wakayos.com")
print(data)