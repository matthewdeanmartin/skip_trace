# TODO

- Doesn't report repo URL status (many are 404)
- Doesn't supress git@gitlab.com as email address
- Doesn't say which file when it finds a email/user/domain in a source file
- Still sometimes doesn't include pypi info like (should always have name/url)
- Owner left blank on pypi individual line
- What is owner/maintainer difference?
- fails to find author in setup.py (what about pyroject.toml/setup.config)
- fails to find in PKG-INFO (why?)

## Broken

- custom domain info should be its own thing separate from whois, e.g. johndoe.com could return 200 with contact info.
- whois/rdap - empty cache files, almost 0 hits (rate limits?), fixation on "org"
- Domain Protection Service/Privacy this or that/Statutory Masking == no data!


## Email addresses with custom domains

- eg. xkcd1172 - custom domain is an identity

## Specific broken packages

- twitter
- xkcd - multiple repos with same user causes multiple evidences
- bloom3 missing info from PKG-INFO  Home-page: http://www.iqianyue.com, Author Wei, etc
- bloom - user has full name on pypi user page, doesn't display in markdown report