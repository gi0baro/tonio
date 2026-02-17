#[cfg(unix)]
use mio::unix::SourceFd;
#[cfg(unix)]
use std::os::fd::RawFd;
#[cfg(windows)]
use std::os::windows::io::{FromRawSocket, RawSocket};

use mio::{Interest, Registry, Token, event::Source as MioSource};

pub(crate) enum Source {
    #[cfg(unix)]
    FD(RawFd),
    // FIXME: on Windows we cannot use `RawSocket` directly, but use `mio::net` types.
    //        thus, we need to find a way to "store" what the FD actually was,
    //        and reconstruct types accordingly in the `impl` blow.
    #[cfg(windows)]
    FD(RawSocket),
}

impl MioSource for Source {
    #[inline]
    fn register(&mut self, registry: &Registry, token: Token, interests: Interest) -> std::io::Result<()> {
        match self {
            #[cfg(unix)]
            Self::FD(inner) => SourceFd(inner).register(registry, token, interests),
            #[cfg(windows)]
            Self::FD(inner) => {
                // FIXME: see above comment
                // let stream_std = unsafe { std::net::TcpStream::from_raw_socket(*inner) };
                // let mut stream = mio::net::TcpStream::from_std(stream_std);
                // stream.register(registry, token, interests)
                panic!()
            }
        }
    }

    #[inline]
    fn reregister(&mut self, registry: &Registry, token: Token, interests: Interest) -> std::io::Result<()> {
        match self {
            #[cfg(unix)]
            Self::FD(inner) => SourceFd(inner).reregister(registry, token, interests),
            #[cfg(windows)]
            Self::FD(inner) => {
                // FIXME: see above comment
                // let stream_std = unsafe { std::net::TcpStream::from_raw_socket(*inner) };
                // let mut stream = mio::net::TcpStream::from_std(stream_std);
                // stream.reregister(registry, token, interests)
                panic!()
            }
        }
    }

    #[inline]
    fn deregister(&mut self, registry: &Registry) -> std::io::Result<()> {
        match self {
            #[cfg(unix)]
            Self::FD(inner) => SourceFd(inner).deregister(registry),
            #[cfg(windows)]
            Self::FD(inner) => {
                // FIXME: see above comment
                // let stream_std = unsafe { std::net::TcpStream::from_raw_socket(*inner) };
                // let mut stream = mio::net::TcpStream::from_std(stream_std);
                // stream.deregister(registry)
                panic!()
            }
        }
    }
}

pub(crate) enum ScheduledIO {
    Add(Token, Interest),
    Upd(Token, Interest),
}

impl ScheduledIO {
    pub fn source(&self) -> Source {
        match self {
            Self::Add(token, _) => Source::FD(token.0.try_into().unwrap()),
            Self::Upd(token, _) => Source::FD(token.0.try_into().unwrap()),
        }
    }
}
