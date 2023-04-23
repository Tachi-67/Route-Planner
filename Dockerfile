# syntax=docker/dockerfile:1
# For finding latest versions of the base image see
# https://github.com/SwissDataScienceCenter/renkulab-docker
ARG RENKU_BASE_IMAGE=renku/renkulab-py:3.9-0.13.1

########################################################
#        Renku install section - do not edit           #

FROM ${RENKU_BASE_IMAGE} as builder

# RENKU_VERSION determines the version of the renku CLI
# that will be used in this image. To find the latest version,
# visit https://pypi.org/project/renku/#history.
ARG RENKU_VERSION=1.11.2

# Install renku from pypi or from github if a dev version
RUN if [ -n "$RENKU_VERSION" ] ; then \
        source .renku/venv/bin/activate ; \
        currentversion=$(renku --version) ; \
        if [ "$RENKU_VERSION" != "$currentversion" ] ; then \
            pip uninstall renku -y ; \
            gitversion=$(echo "$RENKU_VERSION" | sed -n "s/^[[:digit:]]\+\.[[:digit:]]\+\.[[:digit:]]\+\(rc[[:digit:]]\+\)*\(\.dev[[:digit:]]\+\)*\(+g\([a-f0-9]\+\)\)*\(+dirty\)*$/\4/p") ; \
            if [ -n "$gitversion" ] ; then \
                pip install --no-cache-dir --force "git+https://github.com/SwissDataScienceCenter/renku-python.git@$gitversion" ;\
            else \
                pip install --no-cache-dir --force renku==${RENKU_VERSION} ;\
            fi \
        fi \
    fi
#             End Renku install section                #
########################################################

FROM ${RENKU_BASE_IMAGE}

# Uncomment and adapt if code is to be included in the image
# COPY src /code/src

# Uncomment and adapt if your R or python packages require extra linux (ubuntu) software
# e.g. the following installs apt-utils and vim; each pkg on its own line, all lines
# except for the last end with backslash '\' to continue the RUN line
#
# USER root
# RUN apt-get update && \
#    apt-get install -y --no-install-recommends \
#    apt-utils \
#    vim
# USER ${NB_USER}

SHELL ["/bin/bash", "-O", "extglob", "-c"]

ARG ZK_ADDRESS_ARG="iccluster044.iccluster.epfl.ch:2181,iccluster045.iccluster.epfl.ch:2181,iccluster042.iccluster.epfl.ch:2181"
ARG HADOOP_DEFAULT_FS_ARG="hdfs://iccluster044.iccluster.epfl.ch:8020"
ARG YARN_RM_HOSTNAME_ARG="iccluster044.iccluster.epfl.ch"
ARG LIVY_SERVER_ADDRESS_ARG="http://iccluster044.iccluster.epfl.ch:8998"
ARG HBASE_SERVER_ARG="iccluster044.iccluster.epfl.ch"
ARG HIVE_SERVER2_ARG="iccluster044.iccluster.epfl.ch:10000"

ENV CDH_HOME=/opt/cdp
ENV HADOOP_DEFAULT_FS=${HADOOP_DEFAULT_FS_ARG}
ENV HADOOP_HOME=${CDH_HOME}/hadoop-3.1.1
ENV HADOOP_CONF_DIR=${CDH_HOME}/etc/hadoop
ENV HBASE_HOME=${HADOOP_CONF_DIR}
ENV HBASE_CONF_DIR=${HBASE_HOME}
ENV HIVE_JDBC_URL="jdbc:hive2://${ZK_ADDRESS_ARG}/;serviceDiscoveryMode=zooKeeper;zooKeeperNamespace=hiveserver2"
ENV HIVE_SERVER2=${HIVE_SERVER2_ARG}
ENV YARN_RM_HOSTNAME=${YARN_RM_HOSTNAME_ARG}
ENV YARN_RM_ADDRESS=${YARN_RM_HOSTNAME_ARG}:8032
ENV YARN_RM_SCHEDULER=${YARN_RM_HOSTNAME_ARG}:8030
ENV YARN_RM_TRACKER=${YARN_RM_HOSTNAME_ARG}:8031
ENV ZK_ADDRESS=${ZK_ADDRESS_ARG}
ENV LIVY_SERVER_ADDRESS=${LIVY_SERVER_ADDRESS_ARG}
ENV JAVA_HOME=/usr/lib/jvm/java-8-openjdk-amd64
ENV HBASE_SERVER=${HBASE_SERVER_ARG}
ENV LD_LIBRARY_PATH=${HADOOP_HOME}/lib/native/:${LD_LIBRARY_PATH}

USER root
COPY --chown=root:root .dockerbuild/krb5.conf /etc/
RUN <<HEREDOC
    set -euC
    uname -a
    apt-get update
    apt-get install -y --no-install-recommends \
        openjdk-8-jre-headless \
        libsasl2-dev \
        libsasl2-2 \
        libsasl2-modules-gssapi-mit \
        libxml2 \
        libprotobuf17 \
        libz-dev \
        krb5-user \
        jq
    apt-get clean
HEREDOC

# Compile openssl3
RUN <<HEREDOC
    set -euC
    cd /usr/local/src
    wget https://www.openssl.org/source/openssl-3.0.8.tar.gz
    tar -xvf openssl-3.0.8.tar.gz
    cd openssl-3.0.8
    ./config --prefix=/usr/local/ssl --openssldir=/usr/local/ssl shared zlib
    make
    make install_sw
    ln -s /usr/local/ssl/lib64/libcrypto.so.3 /usr/lib/x86_64-linux-gnu/
    cd ../
    rm -rf openssl-3.0.8 openssl-3.0.8.tar.gz
HEREDOC
    

# install hadoop
RUN <<HEREDOC
    set -euC
    mkdir -p ${CDH_HOME}
    cd ${CDH_HOME}
    wget -q https://archive.apache.org/dist/hadoop/core/hadoop-3.1.1/hadoop-3.1.1.tar.gz
    tar --no-same-owner -xf hadoop-3.1.1.tar.gz
    if [ ! -d ${HADOOP_HOME} ]; then
        mv hadoop-3.1.1 ${HADOOP_HOME};
    fi
    mkdir -p ${HADOOP_CONF_DIR}
    rm hadoop-3.1.1.tar.gz
    rm -rf ${HADOOP_HOME}/share/doc/
    rm -rf ${HADOOP_HOME}/sbin/
    rm -rf ${HADOOP_HOME}/etc/
HEREDOC

# hadoop clients config
COPY --chown=root:root <<HEREDOC ${HADOOP_CONF_DIR}/core-site.xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <!--
    <property>
        <name>hadoop.security.authentication</name>
        <value>kerberos</value>
    </property>
    -->
    <property>
        <name>fs.defaultFS</name>
        <value>${HADOOP_DEFAULT_FS}</value>
    </property>
</configuration>
HEREDOC

# shared log4j config
COPY --chown=root:root <<'HEREDOC' ${HADOOP_CONF_DIR}/log4j.properties
log4j.rootLogger=${hadoop.root.logger}
hadoop.root.logger=INFO,console
log4j.appender.console=org.apache.log4j.ConsoleAppender
log4j.appender.console.target=System.err
log4j.appender.console.layout=org.apache.log4j.PatternLayout
log4j.appender.console.layout.ConversionPattern=%d{yy/MM/dd HH:mm:ss} %p %c{2}: %m%n
HEREDOC

# yarn config
COPY --chown=root:root <<HEREDOC ${HADOOP_CONF_DIR}/yarn-site.xml
<?xml version="1.0"?>
<configuration>
    <property>
        <name>yarn.resourcemanager.hostname</name>
        <value>${YARN_RM_HOSTNAME}</value>
    </property>
    <property>
        <name>yarn.resourcemanager.address</name>
        <value>${YARN_RM_ADDRESS}</value>
    </property>
    <property>
        <name>yarn.resourcemanager.resource-tracker.address</name>
        <value>${YARN_RM_TRACKER}</value>
    </property>
    <property>
        <name>yarn.resourcemanager.scheduler.address</name>
        <value>${YARN_RM_SCHEDULER}</value>
    </property>
    <property>
        <name>yarn.resourcemanager.zk-address</name>
        <value>${ZK_ADDRESS}</value>
    </property>
    <property>
        <name>yarn.resourcemanager.principal</name>
        <value>yarn/_HOST@INTRANET.EPFL.CH</value>
    </property>
</configuration>
HEREDOC

# open markdowns as jupytext notebooks
COPY --chown=${NB_USER}:${NB_USER} <<HEREDOC ${HOME}/.jupyter/labconfig/default_setting_overrides.json
{
  "@jupyterlab/docmanager-extension:plugin": {
    "defaultViewers": {
      "markdown": "Jupytext Notebook",
      "python": "Jupytext Notebook"
    }
  }
}
HEREDOC

# sparkmagic pre-install config
COPY --chown=${NB_USER}:${NB_USER} <<HEREDOC ${HOME}/.sparkmagic/config.json
{
  "kernel_python_credentials" : {
    "url": "${LIVY_SERVER_ADDRESS}"
  },
  "kernel_scala_credentials" : {
    "url": "${LIVY_SERVER_ADDRESS}"
  },
  "custom_headers" : {
    "X-Requested-By": "livy"
  },
  "session_configs" : {
    "driverMemory": "1000M",
    "executorMemory": "4G",
    "executorCores": 4,
    "numExecutors": 10
  },
  "cleanup_all_sessions_on_exit": true,
  "server_extension_default_kernel_name": "pysparkkernel",
  "use_auto_viz": true,
  "coerce_dataframe": true,
  "max_results_sql": 1000,
  "pyspark_dataframe_encoding": "utf-8",
  "heartbeat_refresh_seconds": 5,
  "livy_server_heartbeat_timeout_seconds": 60,
  "heartbeat_retry_seconds": 1
}
HEREDOC

# hbase config (not used)
RUN <<HEREDOC
set -euC
cat <<EOF > ${HBASE_CONF_DIR}/hbase-site.xml
<?xml version="1.0" encoding="UTF-8"?>
<configuration>
    <property>
        <name>hbase.rootdir</name>
        <value>hdfs://iccluster044.iccluster.epfl.ch:8020/hbase</value>
    </property>
    <property>
        <name>hbase.client.write.buffer</name>
        <value>2097152</value>
    </property>
    <property>
        <name>hbase.client.pause</name>
        <value>100</value>
    </property>
    <property>
        <name>hbase.client.retries.number</name>
        <value>10</value>
    </property>
    <property>
        <name>hbase.client.scanner.caching</name>
        <value>100</value>
    </property>
    <property>
        <name>hbase.client.keyvalue.maxsize</name>
        <value>10485760</value>
    </property>
    <property>
        <name>hbase.ipc.client.allowsInterrupt</name>
        <value>true</value>
    </property>
    <property>
        <name>hbase.client.primaryCallTimeout.get</name>
        <value>10</value>
    </property>
    <property>
        <name>hbase.client.primaryCallTimeout.multiget</name>
        <value>10</value>
    </property>
    <property>
        <name>hbase.client.scanner.timeout.period</name>
        <value>60000</value>
    </property>
    <!--
    <property>
        <name>hbase.security.authentication</name>
        <value>kerberos</value>
    </property>
    -->
    <property>
        <name>zookeeper.session.timeout</name>
        <value>30000</value>
    </property>
    <property>
        <name>zookeeper.znode.parent</name>
        <value>/hbase</value>
    </property>
    <property>
        <name>zookeeper.znode.rootserver</name>
        <value>root-region-server</value>
    </property>
    <property>
        <name>hbase.zookeeper.quorum</name>
        <value>${ZK_ADDRESS//:+([0-9])}</value>
    </property>
    <property>
        <name>hbase.zookeeper.property.clientPort</name>
        <value>2181</value>
    </property>
</configuration>
EOF
HEREDOC

# update bashrc
RUN <<HEREDOC
    set -euC
    echo 'PATH=${HADOOP_HOME}/bin:${PATH}' >> ${HOME}/.bashrc
HEREDOC

# install the python dependencies
COPY requirements.txt environment.yml /tmp/

RUN <<HEREDOC
    set -euC
    mamba env update -q -f /tmp/environment.yml
    /opt/conda/bin/pip install -r /tmp/requirements.txt --no-cache-dir
    mamba clean -y --all
    mamba env export -n "root"
    jupyter labextension install @jupyterhub/jupyter-server-proxy
    rm -rf ${HOME}/.renku/venv
HEREDOC

COPY --from=builder ${HOME}/.renku/venv ${HOME}/.renku/venv

# post-install be done after installing the python dependencies

# sparkmagic
RUN  <<HEREDOC
    set -euC
    pip install sparkmagic
    jupyter nbextension enable --py --sys-prefix widgetsnbextension
    jupyter labextension install -y --log-level=INFO @jupyter-widgets/jupyterlab-manager
    cd "$(pip show sparkmagic|sed -En 's/Location: (.*)$/\1/p')"
    jupyter-kernelspec install sparkmagic/kernels/sparkkernel
    jupyter-kernelspec install sparkmagic/kernels/pysparkkernel
    jupyter serverextension enable --py sparkmagic
    chown -R ${NB_USER}:${NB_USER} ${HOME}/.local ${HOME}/.sparkmagic ${HOME}/.jupyter ${HOME}/.ipython
HEREDOC

# bash
RUN python -m bash_kernel.install

