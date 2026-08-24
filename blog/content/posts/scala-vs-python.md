---
title: "Scala vs Python"
date: 2015-04-28T17:01:31+01:00
tags:
  - Работа
  - English
summary: "Needed to learn some Scala for the new job, and decided to try it with a small web application together with reading Horstmann’s “Scala for the Impatient”. So, how does it compare with Python?"
---

Needed to learn some Scala for the new job, and decided to try it with a small
web application together with reading Horstmann’s “Scala for the Impatient”
[http://www.horstmann.com/scala/index.html]. So, how does it compare with
Python?

Language itself is pretty great. Not as focused on readability and not so
“pythonic”, but why should it be, at all? And anyway, it’s much cleaner and more
reasonable than Java, while preserving some compatibility. So, let’s move to the
application.

I had some previous experience with Play [https://www.playframework.com/], and
it looks mature and popular enough, so I took it for my project.

First thing I noticed - it took much more time for it to download and install
all necessary modules (only for basic application!) than I got used to with
Python and pip [https://pypi.python.org/pypi/pip].

Second - such a massive framework does not have an ORM. They recommend few libs,
like anorm [https://www.playframework.com/documentation/2.0/ScalaAnorm]  - but
it’s just a thin wrapper around plain SQL, so I’ve tried Slick
[https://github.com/playframework/play-slick], it looked well. Turned out, there
are two “last” versions - stable and beta, and both have interfaces very
different from any 2-3 months old manuals I’ve googled. Bummer! Ok, let’s look
for the docs, right? Wrong, there is no good docs, only a very tiny official
manual (which does not tell how to process prepared queries) and an automatic
man page which only lists methods together with theri parameters, while telling
nothing about what do this method do. Maybe, they think method names are
super-clear, but actually that’s not true, at least for a newbie. So, after a
day of heavy fighting, I gave up and switched to anorm. It’s ugly but at least I
could make it work quickly.

Third, I decided to add a social authentication, and googled up SecureSocial
[http://securesocial.ws/], pac4j  and Silhouette [http://silhouette.mohiva.com/]
. SecureSocial also has 2 “last” versions. Stable doesn’t work with modern Scala
versions, beta doesn’t have any docs available - “just look into the example
code”, author says. Tried to clone example project and run, and it’s not working
at all. Tried pac4j next - it has only one version, thanks Guido, but example
project didn’t work either. Fortunately, when I was going to give up the whole
idea, Silhouette worked.

So, a good language it smashed down with a huge lack of infrastructure, that’s
very clear after using Python for years. Extensive documentation, compact
“quickstart guides” which does not only learn you to plug the lib into your
project, but gives you a working feature at the end… I’ll miss you all!